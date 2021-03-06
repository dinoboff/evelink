import calendar
import functools
import logging
from operator import itemgetter
import re
import time
from urllib import urlencode
import urllib2
from xml.etree import ElementTree

_log = logging.getLogger('evelink.api')

try:
    import requests
    _has_requests = True
except ImportError:
    _log.info('`requests` not available, falling back to urllib2')
    _has_requests = None


def _clean(v):
    """Convert parameters into an acceptable format for the API."""
    if isinstance(v, (list, set, tuple)):
        return ",".join(str(i) for i in v)
    else:
        return str(v)


def parse_ts(v):
    """Parse a timestamp from EVE API XML into a unix-ish timestamp."""
    if v == '':
        return None
    ts = calendar.timegm(time.strptime(v, "%Y-%m-%d %H:%M:%S"))
    # Deal with EVE's nonexistent 0001-01-01 00:00:00 timestamp
    return ts if ts > 0 else None


def get_named_value(elem, field):
    """Returns the string value of the named child element."""
    try:
        return elem.find(field).text
    except AttributeError:
        return None


def get_ts_value(elem, field):
    """Returns the timestamp value of the named child element."""
    val = get_named_value(elem, field)
    if val:
        return parse_ts(val)
    return None


def get_int_value(elem, field):
    """Returns the integer value of the named child element."""
    val = get_named_value(elem, field)
    if val:
        return int(val)
    return val


def get_float_value(elem, field):
    """Returns the float value of the named child element."""
    val = get_named_value(elem, field)
    if val:
        return float(val)
    return val


def get_bool_value(elem, field):
    """Returns the boolean value of the named child element."""
    val = get_named_value(elem, field)
    if val == 'True':
        return True
    elif val == 'False':
        return False
    return None


def elem_getters(elem):
    """Returns a tuple of (_str, _int, _float, _bool, _ts) functions.

    These are getters closed around the provided element.
    """
    _str = lambda key: get_named_value(elem, key)
    _int = lambda key: get_int_value(elem, key)
    _float = lambda key: get_float_value(elem, key)
    _bool = lambda key: get_bool_value(elem, key)
    _ts = lambda key: get_ts_value(elem, key)

    return _str, _int, _float, _bool, _ts


def parse_keyval_data(data_string):
    """Parse 'key: value' lines from a LF-delimited string."""
    keyval_pairs = data_string.strip().split('\n')
    results = {}
    for pair in keyval_pairs:
        key, _, val = pair.strip().partition(': ')

        if 'Date' in key:
            val = parse_ms_date(val)
        elif val == 'null':
            val = None
        elif re.match(r"^-?\d+$", val):
            val = int(val)
        elif re.match(r"-?\d+\.\d+", val):
            val = float(val)

        results[key] = val
    return results

def parse_ms_date(date_string):
    """Convert MS date format into epoch"""

    return int(date_string)/10000000 - 11644473600;

class APIError(Exception):
    """Exception raised when the EVE API returns an error."""

    def __init__(self, code=None, message=None, timestamp=None, expires=None):
        self.code = code
        self.message = message
        self.timestamp = timestamp
        self.expires = expires

    def __repr__(self):
        return "APIError(%r, %r, timestamp=%r, expires=%r)" % (
            self.code, self.message, self.timestamp, self.expires)

    def __str__(self):
        return "%s (code=%d)" % (self.message, int(self.code))


class CacheContext(object):
    """A context Manager wich will try to update the cache value for a key
    if the context leaves with and APIError exception raise or none raised.

    For the cache entry to be updated, the value property needs to change and 
    the duration property needs to be set.
    
    """

    def __init__(self, cache, key):
        self.cache = cache
        self.key = key
        self.value = cache.get(key)
        self._old_value = self.value
        self.duration = None

    def sync(self):
        if self.value == self._old_value:
            return

        if self.duration is None:
            return

        self.cache.put(self.key, self.value, self.duration)
        self._old_value = self.value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """If the context exit on an APIError, tries to update the cache value

        """
        if exc_type is None:
            self.sync()
            return

        if exc_type is not APIError:
            return

        if exc_value.expires is None or exc_value.timestamp is None:
            return

        self.duration = exc_value.expires - exc_value.timestamp
        self.sync()


class APICache(object):
    """Minimal interface for caching API requests.

    This very basic implementation simply stores values in
    memory, with no other persistence. You can subclass it
    to define a more complex/featureful/persistent cache.

    """

    def __init__(self):
        self.cache = {}

    def cache_for(self, key):
        return CacheContext(self, key)

    def get(self, key):
        """Return the value referred to by 'key' if it is cached.

        key:
            a hashable type.
        """
        result = self.cache.get(key)
        if not result:
            return None
        value, expiration = result
        if expiration < time.time():
            del self.cache[key]
            return None
        return value

    def put(self, key, value, duration):
        """Cache the provided value, referenced by 'key', for the given duration.

        key:
            a hashable type.
        value:
            an api response as text (compatible with lxml).
        duration:
            a number of seconds before this cache entry should expire.

        """
        expiration = time.time() + duration
        self.cache[key] = (value, expiration)


class APIResult(tuple):
    
    result = property(itemgetter(0))
    timestamp = property(itemgetter(1))
    expires = property(itemgetter(2))

    def __new__(cls, result, timestamp, expires):
        return tuple.__new__(cls, (result, timestamp, expires,))


    def cache_for(self):
        return self.expires - self.timestamp


class APIRequest(tuple):
    """
    Immutable representation of an api request.

    """

    def __new__(cls, api, path, params=None):
        params = params or {}

        for key in params:
            params[key] = _clean(params[key])

        _log.debug("Calling %s with params=%r", path, params)

        if api.api_key:
            _log.debug("keyID and vCode added")
            params['keyID'] = api.api_key[0]
            params['vCode'] = api.api_key[1]

        return tuple.__new__(
            cls, 
            (
                api.CACHE_VERSION,
                api.base_url,
                path,
                tuple(sorted(params.iteritems())),
            )
        )

    cache_version = property(itemgetter(0))
    base_url = property(itemgetter(1))
    path = property(itemgetter(2))
    params = property(itemgetter(3))


    @property
    def encoded_params(self):
        return urlencode(self.params)

    @property
    def absolute_url(self):
        return "https://%s/%s.xml.aspx" % (self.base_url, self.path)

    def send(self, api):
        """
        Send the request and return the body as a string.

        Raise an exception for a failed request (including 4xx and 5xx 
        response error code).
        
        TODO: handle failed request better. The API wrapper needs to know 
        if the error was due to the network, to a bad key, to a bad request or  
        or to the API server.

        """
        try:
            if self.params:
                # POST request
                _log.debug("POSTing request")
                r = urllib2.urlopen(self.absolute_url, self.encoded_params)
            else:
                # GET request
                _log.debug("GETting request")
                r = urllib2.urlopen(self.absolute_url)

            result = r.read()
            r.close()
            return result
        except urllib2.URLError as e:
            # TODO: Handle this better?
            raise e

    def __str__(self):
        """
        Current cache key implementation.
        
        TODO: include base_url?

        """
        return '%s-%s' % (self.cache_version, hash(self[2:4]),)


class APIRequestRequests(APIRequest):
    
    def send(self, api):
        _log.debug("sending request using requests")
        if api.session is None:
            api.session = requests.Session()

        try:
            if self.params:
                # POST request
                _log.debug("POSTing request")
                r = api.session.post(
                    self.absolute_url, 
                    params=self.encoded_params
                )
            else:
                # GET request
                _log.debug("GETting request")
                r = api.session.get(self.absolute_url)
            return r.content
        except requests.exceptions.RequestException as e:
            # TODO: Handle this better?
            raise e


class API(object):
    """A wrapper around the EVE API."""

    CACHE_VERSION = 1

    if _has_requests:
        Request = APIRequestRequests
    else:
        Request = APIRequest

    def __init__(self, base_url="api.eveonline.com", cache=None, api_key=None):
        self.base_url = base_url

        cache = cache or APICache()
        if not isinstance(cache, APICache):
            raise ValueError("The provided cache must subclass from APICache.")
        self.cache = cache

        if api_key and len(api_key) != 2:
            raise ValueError("The provided API key must be a tuple of (keyID, vCode).")
        self.api_key = api_key
        self._set_last_timestamps()
        self.session = None

    def _set_last_timestamps(self, current_time=0, cached_until=0):
        self.last_timestamps = {
            'current_time': current_time,
            'cached_until': cached_until,
        }

    def get(self, path, params=None):
        """Request a specific path from the EVE API.

        The supplied path should be a slash-separated path
        frament, e.g. "corp/AssetList". (Basically, the portion
        of the API url in between the root / and the .xml bit.)

        """
        req = self.Request(self, path, params)
        with self.cache.cache_for(str(req)) as cache:
            if cache.value is None:
                cache.value = req.send(self)
            else:
                _log.debug("Cache hit, returning cached payload")
            
            results = self.process_response(cache.value)
            cache.duration = results.cache_for()

        return results

    def process_response(self, response):
        """return the result (Element object), currentTime and cacheUntil 
        elements from an api call response.

        """
        tree = ElementTree.fromstring(response)
        current_time = get_ts_value(tree, 'currentTime')
        expires_time = get_ts_value(tree, 'cachedUntil')
        self._set_last_timestamps(current_time, expires_time)

        # TODO: use the http response code instead of looking for the element
        error = tree.find('error') 
        if error is not None:
            code = error.attrib['code']
            message = error.text.strip()
            exc = APIError(code, message, current_time, expires_time)
            _log.error("Raising API error: %r" % exc)
            raise exc

        result = tree.find('result')
        return APIResult(result, current_time, expires_time)


def auto_api(func):
    """A decorator to automatically provide an API instance.

    Functions decorated with this will have the api= kwarg
    automatically supplied with a default-initialized API()
    object if no other API object is supplied.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if 'api' not in kwargs:
            kwargs['api'] = API()
        return func(*args, **kwargs)
    return wrapper


# vim: set ts=4 sts=4 sw=4 et:
