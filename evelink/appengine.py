from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from evelink import api
import time


class AppEngineAPIRequest(api.APIRequest):
    
    def send(self, api):
        result = urlfetch.fetch(
            url=self.absolute_url,
            payload=self.encoded_params,
            method=urlfetch.POST if self.params else urlfetch.GET,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
                    if self.params else {}
        )

        if result.status_code != 200:
            raise ValueError("Bad result from server: {}".format(result.status_code))
        return result.content

    @ndb.tasklet
    def send_async(self, api):
        ctx = ndb.get_context()
        result = yield ctx.urlfetch(
            url=self.absolute_url,
            payload=self.encoded_params,
            method=urlfetch.POST if self.params else urlfetch.GET,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
                    if self.params else {}
        )

        if result.status_code != 200:
            raise ValueError("Bad result from server: {}".format(result.status_code))
        raise ndb.Return(result.content)


class AppEngineAPI(api.API):
    """
    Subclass of api.API that is compatible with Google Appengine.

    """
    Request = AppEngineAPIRequest
    
    def __init__(self, base_url="api.eveonline.com", cache=None, api_key=None):
        cache = cache or AppEngineCache()
        super(AppEngineAPI, self).__init__(base_url=base_url,
                cache=cache, api_key=api_key)

    @ndb.tasklet
    def get_async(self, path, params):
        # req = self.Request(self, path, params)
        # key = str(req)
        # # TODO: add async method
        # response = self.cache.get(key)
        # cached = response is not None

        # if not cached:
        #     response = yield req.send_async(self)

        # results = self.process_response(response)

        # if not cached:
        #     self.cache.put(key, response, results.cache_for())

        # raise ndb.Return(results)
        req = self.Request(self, path, params)
        # TODO: replace by async method
        with self.cache.cache_for(str(req)) as cache:
            if cache.value is None:
                cache.value = yield req.send_async(self)
            
            results = self.process_response(cache.value)
            cache.duration = results.cache_for()

        raise ndb.Return(results)


class AppEngineCache(api.APICache):
    """Memcache backed APICache implementation."""
    def get(self, key):
        return memcache.get(key)

    def put(self, key, value, duration):
        if duration < 0:
            duration = time.time() + duration
        memcache.set(key, value, time=duration)


class EveLinkCache(ndb.Model):
    value = ndb.PickleProperty()
    expiration = ndb.IntegerProperty()


class AppEngineDatastoreCache(api.APICache):
    """An implementation of APICache using the AppEngine datastore."""

    def __init__(self):
        super(AppEngineDatastoreCache, self).__init__()

    def get(self, cache_key):
        db_key = ndb.Key(EveLinkCache, cache_key)
        result = db_key.get()
        if not result:
            return None
        if result.expiration < time.time():
            db_key.delete()
            return None
        return result.value

    def put(self, cache_key, value, duration):
        expiration = int(time.time() + duration)
        cache = EveLinkCache.get_or_insert(cache_key)
        cache.value = value
        cache.expiration = expiration
        cache.put()
