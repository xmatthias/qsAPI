# -*- coding: UTF-8 -*-

'''
@author:     Rafael Sanz
@contact:    rafael.sanz@selab.es
@Copyright 2016 <Rafael Sanz - (R)SELAB>

This software is MIT licensed (see terms below)

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
    modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the 
    Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
    LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR 
    IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import sys, os.path
from distutils.version import LooseVersion as Version
import requests as req
import urllib.parse as up
import random, string, json, uuid
import logging

__version__ = "1.7"
__updated__ = '19/03/2018'



class _Controller(object):
    """ Handler REST-API QRS"""
       
    _referer='Mozilla/5.0 (Windows NT 6.3; Win64; x64) qsAPI APIREST (QSense)'
    
    try:
        from requests_ntlm import HttpNtlmAuth
    except ImportError:
        HttpNtlmAuth=None  
    
    def __init__(self, proxy, port, preffix, certificate, verify, user, verbosity, logName):
        ''' 
            @Function setup: Setup the connection and initialize handlers
            @param proxy: hostname to connect
            @param port: port number
            @param certificate: path to .pem client certificate
            @param verify: false to trust in self-signed certificates
            @param user: dict with keys {userDirectory:, userID:, password:}
            @param verbosity: debug level
            @param logger: logger instance name
        '''
        self.proxy    = proxy
        self.port     = str(port)
        self.baseurl  = None
        self.request  = None
        self.response = None
        self.session  = None
        if isinstance(user, dict):
            self.setUser(user.get('userDirectory'), user.get('userID'), user.get('password'))
        else:
            self.setUser(*user)
          
        self.chunk_size = 512 #Kb
        
        self.log=logging.getLogger(logName)
        if not self.log.hasHandlers():
            self.log.addHandler(logging.StreamHandler(sys.stdout))
        self.log.setLevel(verbosity)
        
        #TODO: mover schema a configurable
        self.baseurl= 'https://{host}:{port}{prf}'.format(host=proxy, port=str(port), prf=preffix)
        
        if isinstance(certificate, str):
            (base,ext)=os.path.splitext(certificate)
            self.cafile=(base+ext, base+'_key'+ext)
            self.log.debug('CERTKEY: %s%s', base, ext)
        elif isinstance(certificate, tuple):
            self.cafile=certificate
            self.log.debug('CERT: %s',certificate)
        else:
            self.cafile=False
            
        self._verify=bool(verify)
        
        if not self._verify:
            req.packages.urllib3.disable_warnings()
        
        self.session=req.Session()
        
        if self.HttpNtlmAuth:
            self.log.debug('NTLM authentication enabled')
            self.session.auth = self.HttpNtlmAuth('{domain}\\{user}'.format(domain=self.UserDirectory, user=self.UserId), self.Password)
        
        
        
        
    def setUser(self, userDirectory, userID, password=None):
        self.UserDirectory=userDirectory
        self.UserId = userID
        self.Password=password
        
        
        
    def _params_prepare(self, param, xhd={}):
                
        par=dict({'Xrfkey': ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))})

        if isinstance(param, dict):
            for p,v in param.items():
                if v is not None:
                    if isinstance(v, bool):
                        par[p]=str(v).lower()
                    else:
                        par[p]=str(v)
                    self.log.debug(" >> %s=>%s",p , par[p])
                else:
                    self.log.debug(" >> %s=>(default)", p)
            
        
        hd= { 'User-agent': self._referer,
              'Pragma': 'no-cache',
              'X-Qlik-User': 'UserDirectory={directory}; UserId={user}'.format(directory=self.UserDirectory, user=self.UserId),
              'x-Qlik-Xrfkey': par.get('Xrfkey'),
              'Accept': 'application/json',
              'Content-Type': 'application/json'}
        
        #if self.vproxy:
        #    hd['X-Qlik-Virtual-Proxy-Prefix']=self.vproxy
        
        #TODO: PROVISIONAL
        #hd['X-Qlik-Virtual-Proxy-Prefix']='proxy'
        
        hd.update(xhd)
        return(par, hd)  
    
    
    def _params_update(self, url, par):
        scheme, netloc, path, query, fragment=up.urlsplit(url)
        p=up.parse_qs(query)
        p.update(par)
        query=up.urlencode(p,doseq=True,quote_via=up.quote)
        return up.urlunsplit((scheme, netloc, path, query, fragment))
        
        
    
       
    def call(self, method='GET', apipath='/', param=None, data=None, files=None):
        """ initialize control structure """
               
        if str(method).upper() not in ('GET', 'POST', 'PUT', 'DELETE'):
            raise Exception('invalid method <{0}>'.format(method))
       
        self.log.info('API %s <%s>', method[:3], apipath)
        
        (par,hd)=self._params_prepare(param, {} if files is None else {'Content-Type': 'application/vnd.qlik.sense.app'})
        
        # Build the request        
        self.response= None
            
        url=self._params_update(self.baseurl+apipath, par)
        
        
        self.request=req.Request(method, url, headers=hd, data=data, files=files, auth=self.session.auth)
        pr=self.session.prepare_request(self.request)
                
        self.log.debug('SEND: %s', self.request.url)
                
        # Execute the HTTP request
        self.response = self.session.send(pr, cert=self.cafile, verify=self._verify, allow_redirects=False)
        rc=0
        while self.response.is_redirect:
            rc+=1
            if rc > self.session.max_redirects:
                raise req.HTTPError('Too many redirections')
            self.session.rebuild_auth(self.response.next, self.response)
            self.response.next.prepare_headers(hd)
            self.response.next.prepare_cookies(self.response.cookies)
            self.response.next.url=self._params_update(self.response.next.url, par)
            self.log.debug('REDIR: %s', self.response.next.url)
            self.response = self.session.send(self.response.next, verify=self._verify, allow_redirects=False)
            
        self.log.debug('RECV: %s',self.response.text)
        
        return(self.response)



    def download(self, apipath, filename, param=None):
        """ initialize control structure """
                   
        self.log.info('API DOWN <%s>', apipath)

        (par,hd)=self._params_prepare(param)
        
        # Build the request        
        self.response= None
        
        #TODO: mejorar
        #url='{0}/{1}?{2}'.format(self.baseurl, apipath.lstrip('/'), up.urlencode(par))
        url=self._params_update('https://{host}:{port}'.format(host=self.proxy, port=str(self.port))+apipath, par)
     
        self.log.debug('__SEND: %s',url)
                
        # Execute the HTTP request 
        self.request = self.session.get(url, headers=hd, cert=self.cafile, verify=self._verify, stream=True, auth=self.session.auth)
            
        with open(filename, 'wb') as f:
            self.log.info('__Downloading (in %sKb blocks): ', str(self.chunk_size))
            
            #download in 512Kb blocks
            for chunk in self.request.iter_content(chunk_size=self.chunk_size << 10): 
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                        
            self.log.info('__Saved: %s', os.path.abspath(filename))
        
        return(self.request)

    
    
    def upload(self, apipath, filename, param=None):
        """ initialize control structure """
        
        class upload_in_chunks(object):
            def __init__(self, filename, chunksize=512):
                self.filename = filename
                self.chunksize = chunksize << 10
                self.totalsize = os.path.getsize(filename)
                self.readsofar = 0
        
            def __iter__(self):
                with open(self.filename, 'rb') as file:
                    while True:
                        data = file.read(self.chunksize)
                        if not data:
                            break
                        self.readsofar += len(data)
                        yield data
        
            def __len__(self):
                return self.totalsize
                       
        self.log.info('API UPLO <%s>', apipath)

        (par,hd)=self._params_prepare(param, {'Content-Type': 'application/vnd.qlik.sense.app'})
           
        # Build the request        
        self.response= None
        #url='{0}/{1}?{2}'.format(self.baseurl, apipath.lstrip('/'), up.urlencode(par))
        url=self._params_update(self.baseurl+apipath, par)
             
        self.log.debug('__SEND: %s', url)

        # Execute the HTTP request 
        self.log.info('__Uploading {:,} bytes'.format(os.path.getsize(filename)))
            
        #TODO: mover a session
        #upload
        self.request = self.session.post(url, headers=hd, cert=self.cafile, verify=self._verify, \
                                data=upload_in_chunks(filename, self.chunk_size), auth=self.session.auth)
            
        self.log.info('__Done.')                
            
        return(self.request)


    
    
    def get(self, apipath='/qrs/about/api/description', param=None):
        '''
        @Function get: generic purpose call
        @param apipath: uri REST path
        @param param : whatever other param needed in form a dict
                      (example: {'filter': "name eq 'myApp'} )
        '''
        return self.call('GET', apipath, param)
    
    
    
    def post(self, apipath, param=None, data=None, files=None):
        '''
        @Function post: generic purpose call
        @param apipath: uri REST path
        @param param : whatever other param needed in form a dict
                      (example: {'filter': "name eq 'myApp'} )
        @param data : stream data input (native dict/list structures are json formated)
        @param files : metafile input 
        '''
        if isinstance(data,dict) or isinstance(data,list):
            data=json.dumps(data)
        return self.call('POST', apipath, param, data, files)
    
    
    
    def put(self, apipath, param=None, data=None):
        '''
        @Function put: generic purpose call
        @param apipath: uri REST path
        @param param : whatever other param needed in form a dict
                      (example: {'filter': "name eq 'myApp'} )
        @param data : stream data input (native dict/list structures are json formated)
        '''
        if isinstance(data,dict) or isinstance(data,list):
            data=json.dumps(data)
        return self.call('PUT', apipath, param, data)
    
    
    
    def delete(self, apipath, param=None):
        '''
        @Function delete: generic purpose call
        @param apipath: uri REST path
        @param param : whatever other param needed in form a dict
                      (example: {'filter': "name eq 'myApp'} )
        '''
        return self.call('DELETE', apipath, param)

    
    

class QPS(object):
    '''Qlik Sense Proxy Service REST API'''
    
    VERSION_API= Version(__version__)
    
    #TODO: vproxy --> default vproxy y no tratar dinamicamente
    def __init__(self, proxy='localhost', port=4243, vproxy=None, certificate=None, verify=False, \
                 user={'userDirectory':'internal', 'userID':'sa_repository', 'password': None}, \
                 verbosity='INFO', logger='qsapi'):  
        
        if ':' in proxy:
            (proxy, port) = proxy.split(':')
        
        preffix='/qps/{}'.format(vproxy.rstrip('/')) if vproxy else '/qps'
        self.driver=_Controller(proxy, port, preffix, certificate, verify, user, verbosity, logger)

        
    #TODO: en funciones QPS, virtual proxy deberia ser un parametro opcional a la funcion
    def GetUser(self, directory, user):
        '''
        @Function: This returns all proxy sessions that a user (identified by {directory} and {user}) has.
        '''
        apipath='/user/{directory}/{id}'.format(directory=directory, id=user)
        return self.driver.get(apipath)

    
    
    def DeleteUser(self, directory, user):
        '''
        @Function: This is part of the Logout API. The directory and ID are the same UserDirectory and UserId as those that were sent in POST /qps/{virtual proxy/}ticket.
                    A list of all proxy sessions that were connected to the deleted user is returned. 
        '''
        apipath='/user/{directory}/{id}'.format(directory=directory, id=user)
        return self.driver.delete(apipath)
    

    
    def GetSession(self, pId):
        '''
        @Function: This returns the proxy session identified by {id}.
        '''
        apipath='/session/{id}'.format(id=pId)
        return self.driver.get(apipath)
    
    
    def DeleteSession(self, pId):
        '''
        @Function: Delete the proxy session identified by {id}.
        '''
        apipath='/session/{id}'.format(virtual_proxy=self.driver.preffix, id=pId)
        return self.driver.delete(apipath)




class QRS(object):
    '''Qlik Sense Repository Service REST API'''
    
    VERSION_API= Version(__version__)
    
    
    def __init__(self, proxy='localhost', port=4242, vproxy=None, certificate=None, verify=False, \
                 user={'userDirectory':'internal', 'userID':'sa_repository', 'password': None}, \
                 verbosity='INFO', logger='qsapi'):
        
        if ':' in proxy:
            (proxy, port) = proxy.split(':')
            
        preffix='/{}/qrs'.format(vproxy.rstrip('/')) if vproxy else '/qrs'    
        self.driver=_Controller(proxy, port, preffix, certificate, verify, user, verbosity, logger)
        
        self.VERSION_SERVER=self.getServerVersion()
        if self.VERSION_API > self.VERSION_SERVER:
            raise Exception('<server version mismatch, API:{0} > Server:{1}'.format(self.VERSION_API, self.VERSION_SERVER))
        else:
            self.driver.log.info('Server version: {0}'.format(self.VERSION_SERVER))


    
    def _toDict(self, response, uid='full', key='name', attr='id'):
        r={}
        if response.ok:
            j=response.json()
            if uid != "full":
                if isinstance(attr, str):
                    r[j.get(key)]=j.get(attr)
                elif isinstance(attr, list):
                    ra={}
                    for a in attr:
                        ra[a]=(j.get(a))
                    r[j.get(key)]=ra
                else:
                    raise TypeError('attr argument must be a str or list')
            else:               
                for x in j:
                    if isinstance(attr, str):
                        r[x.get(key)]=x.get(attr)
                    elif isinstance(attr, list):
                        ra={}
                        for a in attr:
                            ra[a]=(x.get(a))
                        r[x.get(key)]=ra
                    else:
                        raise TypeError('attr argument must be a str or list')
        
        return(r)
    


    def ping(self):
        '''
        @return: "Ping successful", if there are no problems contacting the Qlik Sense Repository Service (QRS).
        '''
        return self.driver.call('GET', '/ssl/ping')



        
    def getServerVersion(self):
        '''
        @Function: retrieve the server version
        '''
        return Version(self.driver.call('GET', '/about').json().get('buildVersion'))

 
 
    
    def getAbout(self):
        '''
        @Function: Get information on the Qlik Sense repository, including version, database provider, and whether the node is the central node of the site or not.
        '''
        return self.driver.get('/about').json()
    
 
    
    def count(self, pType, pFilter=None):
        '''
        @Function: generic purpose call
        @param pType: entity to count
        @param pFilter: filter the entities before calculating the number of entities. 
        @return : integer from json response
        '''
        return self.driver.get('/{0}/count'.format(pType), param={'filter':pFilter}).json()['value']
 
    
    
    def getDescription(self, extended='False', method=None, outformat='JSON'):
        '''@Function : List all paths available in the Qlik Sense Repository Service (QRS) API. Optionally, return extended information, endpoints that use a specific HTTP verb, or the return values in JSON format.
           @param extended: If true, returns the following:
                The type (if any) that needs to be included in the body.
                The type of return value (if any).
                If the endpoint is automatically generated or not.
           @param method:  If set to an HTTP verb (GET, PUT, POST, or DELETE), only endpoints that use the verb are returned.
           @param outformat:  If set to "JSON", the return value is given in JSON format. 
        '''
            
        param={'extended': extended in ('True', 'true', True),
               'method'  : method,
               'format'  : outformat}
        
        return self.driver.get('/about/api/description', param).json()



    def getEnum(self):
        '''@Function: Get all enums that are used by the public part of the Qlik Sense Repository Service (QRS) API.
        '''
        return self.driver.get('/about/api/enums').json()



    #=========================================================================================

    
    
    def AppDictAttributes(self, guid='full', key='name', attr='id'):
        '''@Function: retrieve a mapping of apps attributes
           @param pId: limmit the scope to the App {GUID}
           @param key: the attribute to be the key
           @param attr: the attribute value to retrieve (single value or list)
           @return: dict(key:attr)
        '''
        
        apipath='/app/{guid}'.format(guid=guid)
        
        return self._toDict(self.driver.get(apipath), guid, key, attr)    
        
    

    def AppCopy(self, pId, name=None):
        '''
        @Function: Copy an existing app, identified by {id}. Optionally, provide a name for the copy.
        @param pId: app identifier
        @param name: Name of the app
        '''
        param={'name':name}
        return self.driver.post('/app/{id}/copy'.format(id=pId), param).json()


    
    def AppExport(self, pId, filename=None):
        '''
        @Function: Get an export qvf for an existing app, identified by {id}.
        @param pId: app GUI
        @param filename: target path filename
        @return : stored application
        '''
        file= filename if filename else pId+'.qvf'
        if self.VERSION_SERVER < "17.0":
            #DEPRECATED API since November-2017
            self.driver.log.info('Server version: %s, using legacy API', self.VERSION_SERVER)
            r=self.driver.get('/app/{id}/export'.format(id=pId))
            if r.ok:
                r=self.driver.download('/download/app/{appId}/{TicketId}/{fileName}'.format(appId=pId, TicketId=r.json()['value'], fileName=file), file)
            return(r)
        
        #Current API method
        r=self.driver.post('/app/{id}/export/{token}'.format(id=pId, token=uuid.uuid4()))
        if r.ok:
            r=self.driver.download(r.json()['downloadPath'], file)
        return(r)




    def AppUpload(self, filename, pName, keepdata=None):
        '''
        @Function: Upload a filename.qvf into Central Node.
        @param filename: target path filename
        @param name: target app name
        @param keepdata: Exclude the app data when uploading the app (when it is implemented)
        '''
        param ={'name'    :pName,
                'keepdata':keepdata}
        return self.driver.upload('/app/upload', filename, param)

    
    def AppGet(self, pId='full', pFilter=None):
        '''
        @Function: retrieve App information
        @param pId: App GUID 
        @param pFilter: filter the entities before calculating the number of entities. 
        @return : json response
        '''
        return self.driver.get('/app/{id}'.format(id=pId), param={'filter':pFilter}).json()
    
    
    
    def AppMigrate(self, pId):
        '''
        @Function: Migrate an app so that it can be used in the currently installed version of Qlik Sense.
                    Normally, this is done automatically
        @param pId: app identifier
        '''
        return self.driver.put('/app/{id}/migrate'.format(id=pId))
    
            
    
    def AppReload(self, pId):
        '''
        @Function: Reload an app
        @param pId: app identifier
        '''
        return self.driver.post('/app/{id}/reload'.format(id=pId))


    def AppPublish(self, pId, streamId, name=None):
        '''
        @Function: Publish an existing app, identified by {id}, to the stream identified by {streamid}.
        @param pId: app identifier
        @param streamId: stream identifier
        @param name: optional alternate name
        '''
        param ={'stream' :streamId,
                'name'   :name}
        return self.driver.put('/app/{id}/publish'.format(id=pId), param)
    
    
    def AppUpdate(self, pId, pData):
        '''
        @Function: update App info referenced 
        @param pId: App GUID 
        '''
        return self.driver.put('/app/{id}'.format(id=pId), data=pData)
    
    
    def AppReplace(self, pId, pAppId):
        '''
        @Function: Replace an app, identified by {appid}, with the app identified by {id}. 
        @param pId: App GUID 
        @param pAppId: target App GUID

        If the replaced app is published, only the sheets that were originally published with the app are replaced.
        If the replaced app is not published, the entire app is replaced.
        '''
        param ={'app' :pAppId}
        return self.driver.put('/app/{id}/replace'.format(id=pId), param)
    
    
    def AppDelete(self, pId):
        '''
        @Function: delete App referenced 
        @param pId: App GUID 
        '''
        return self.driver.delete('/app/{id}'.format(id=pId))
    
    
    #=========================================================================================
    
    
    def StreamCreate(self, pName, pProperties=[] , pTags=[], pUUID=None):
        '''
        @Function: create a Stream
        @param pName: Stream Name 
        @param pUID: Stream UUID
        @param pProperties: list of dict with properties definitions.
        @param pTags: list of dict with tag definitions 
        @return : json response
        '''
        param={'name': pName,
               'customProperties': pProperties,
               'tags': pTags}
        
        if pUUID is not None:
            param['id']=pUUID
                 
        return self.driver.post('/stream', data=param).json()
    
    
    
    def StreamGet(self, pId='full', pFilter=None):
        '''
        @Function: retrieve Stream information
        @param pId: Stream GUID 
        @param pFilter: filter the entities before calculating the number of entities. 
        @return : json response
        '''
        return self.driver.get('/stream/{id}'.format(id=pId), param={'filter':pFilter}).json()
    
    
    
    def StreamUpdate(self, pId, pData):
        '''
        @Function: update Stream info referenced 
        @param pId: Stream GUID 
        '''
        return self.driver.put('/stream/{id}'.format(id=pId), data=pData)
    
    
    
    def StreamDelete(self, pId):
        '''
        @Function: delete Stream referenced 
        @param pId: Stream GUID 
        @return : json response
        '''
        return self.driver.delete('/stream/{id}'.format(id=pId))
    
    
    
    def StreamDictAttributes(self, pStreamID='full', key='name', attr='id'):
        '''@Function: retrieve a mapping of Stream attributes
           @param pStreamID: limmit the scope to the Stream {UID}
           @param key: the attribute to be the key
           @param attr: the attribute value to retrieve (single value or list)
           @return: dict(key:attr)
        '''
        apipath='/stream/{uid}'.format(uid=pStreamID)            
        return self._toDict(self.driver.get(apipath), pStreamID, key, attr) 
    
    
    #=========================================================================================     
    
    
    def UserGet(self, pUserID='full', pFilter=None):
        '''
        @Function: retrieve user information
        @param pUserID: User id 
        @param pFilter: filter the entities before calculating the number of entities. 
        @return : json response
        '''
        return self.driver.get('/user/{id}'.format(id=pUserID), param={'filter':pFilter}).json()
    
    
    def UserUpdate(self, pUserID, pData):
        '''
        @Function: update user information
        @param pUserID: User id 
        @param pData: json with user information. 
        @return : json response
        '''
        return self.driver.put('/user/{id}'.format(id=pUserID), data=pData)
    
    
    def UserDelete(self, pUserID):
        '''
        @Function: retrieve user information
        @param pUserID: User id 
        @param pFilter: filter the entities before calculating the number of entities. 
        @return : json response
        '''
        return self.driver.delete('/user/{id}'.format(id=pUserID))
    
    
    def UserDictAttributes(self, pUserID='full', key='name', attr='id'):
        '''@Function: retrieve a mapping of user attributes
           @param pUserID: limmit the scope to the User {UID}
           @param key: the attribute to be the key
           @param attr: the attribute value to retrieve (single value or list)
           @return: dict(key:attr)
        '''
        apipath='/user/{uid}'.format(uid=pUserID)            
        return self._toDict(self.driver.get(apipath),pUserID,key,attr)
    
    
    #=========================================================================================
    

   
    def SystemRules(self, pFilter=None):
        '''
        @Function: Get the system rules
        '''
        return self.driver.get('/systemrule/full', {'filter':pFilter}).json()
   
   
    
    def SystemRulesDictAttributes(self, pRuleID='full', key='name', attr='id'):
        '''@Function: retrieve a mapping of rules attributes
           @param pRuleID: limmit the scope to the Rule {UID}
           @param key: the attribute to be the key
           @param attr: the attribute value to retrieve (single value or list)
           @return: dict(key:attr)
        '''
        apipath='/systemrule/{uid}'.format(uid=pRuleID)            
        return self._toDict(self.driver.get(apipath),pRuleID,key,attr)
    
    
    
    #=========================================================================================
    
    
    def PropertiesGet(self, pFilter=None):
        '''
        @Function: Get the system rules
        '''
        return self.driver.get('/custompropertydefinition/full', {'filter':pFilter}).json()
        #TODO: Complete Properties methods


    #=========================================================================================
    
    

if __name__ == "__main__":
    '''
    Alternative command line invocation, examples:
        python qsAPI.py -s myServer -c dir/client.pem -Q QRS AppDictAttributes
        python qsAPI.py -s myServer -c dir/client.pem -Q QRS -v INFO AppExport d8b120d7-a6e4-42ff-90b2-2ac6a3d92233 
        python qsAPI.py -s myServer -c dir/client.pem -Q QRS -v INFO AppReload d8b120d7-a6e4-42ff-90b2-2ac6a3d92233
        
    '''
    from argparse import ArgumentParser
    import inspect
    from pprint import pprint
    
    parser = ArgumentParser(description='qsAPI for QlikSense')
    parser.add_argument('-s', dest='server', required=True)
    #parser.add_argument('-c', dest='certificate', required=True)
    parser.add_argument('-c', dest='certificate', required=False)
    parser.add_argument('-p', dest='vproxy', required=False)
    parser.add_argument("-Q", dest="api", choices=['QPS','QRS'], default='QRS', required=True, help="service API")
    parser.add_argument(dest='method', nargs='+', help='API method to call')
    parser.add_argument("-v", dest="verbose", choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'], default='INFO', help="set verbosity level")
    parser.add_argument('--version', action='version', version='tools {}'.format(__version__))
    
    # Process arguments
    args = parser.parse_args()
    Q=QPS if args.api == 'QPS' else QRS

    qr=Q(proxy=args.server, vproxy=args.vproxy, certificate=args.certificate, verbosity=args.verbose)
    m=[x for x,y in inspect.getmembers(Q) if not x.startswith('_') ]
    
    cmd=args.method[0]
    if cmd not in m:
        print('ERROR: "{}" is not a method of {}, expected=> {}'.format(cmd, args.api, m))
        sys.exit(-1)
    
    pprint(getattr(qr, cmd)(*args.method[1:]))
    sys.exit(0)

    
