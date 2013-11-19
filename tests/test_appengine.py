import sys
import mock
import unittest2 as unittest

try:
    from google.appengine.ext import testbed
    from google.appengine.ext import ndb
except ImportError:
    NOGAE = True
    ndb = mock.Mock()
else:
    from evelink import appengine
    from evelink import eve
    NOGAE = False


@unittest.skipIf(sys.version_info < (2, 7,), 'GAE requires python 2.7')
@unittest.skipIf(NOGAE, 'No GAE SDK found')
class GAETestCase(unittest.TestCase):
    """
    Those test cases require python 2.6 and the Google App Engine SDK 
    to be installed.

    """


class DatastoreCacheTestCase(GAETestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_memcache_stub()
        self.testbed.init_datastore_v3_stub()

    def tearDown(self):
        self.testbed.deactivate()

    def test_cache_datastore(self):
        cache = appengine.AppEngineDatastoreCache()
        cache.put('foo', 'bar', 3600)
        cache.put('bar', 1, 3600)
        cache.put('baz', True, 3600)
        self.assertEqual(cache.get('foo'), 'bar')
        self.assertEqual(cache.get('bar'), 1)
        self.assertEqual(cache.get('baz'), True)

    def test_expire_datastore(self):
        cache = appengine.AppEngineDatastoreCache()
        cache.put('baz', 'qux', -1)
        self.assertEqual(cache.get('baz'), None)


class MemcacheCacheTestCase(GAETestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_memcache_stub()

    def tearDown(self):
        self.testbed.deactivate()

    def test_cache_memcache(self):
        cache = appengine.AppEngineCache()
        cache.put('foo', 'bar', 3600)
        cache.put('bar', 1, 3600)
        cache.put('baz', True, 3600)
        self.assertEqual(cache.get('foo'), 'bar')
        self.assertEqual(cache.get('bar'), 1)
        self.assertEqual(cache.get('baz'), True)

    def test_expire_memcache(self):
        cache = appengine.AppEngineCache()
        cache.put('baz', 'qux', -1)
        self.assertEqual(cache.get('baz'), None)


class AppEngineAPITestCase(GAETestCase):

    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_memcache_stub()
        self.test_xml = r"""
            <?xml version='1.0' encoding='UTF-8'?>
            <eveapi version="2">
                <currentTime>2009-10-18 17:05:31</currentTime>
                <result>
                    <rowset>
                        <row foo="bar" />
                        <row foo="baz" />
                    </rowset>
                </result>
                <cachedUntil>2009-11-18 17:05:31</cachedUntil>
            </eveapi>
        """.strip()

    def tearDown(self):
        self.testbed.deactivate()

    @mock.patch('google.appengine.api.urlfetch.fetch')
    def test_get(self, mock_urlfetch):
        mock_urlfetch.return_value.status_code = 200
        mock_urlfetch.return_value.content = self.test_xml

        api = appengine.AppEngineAPI()
        result = api.get('foo/Bar', {'a':[1,2,3]})

        rowset = result.find('rowset')
        rows = rowset.findall('row')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].attrib['foo'], 'bar')
        self.assertEqual(api.last_timestamps, {
            'current_time': 1255885531,
            'cached_until': 1258563931,
        })


class EveChar(ndb.Model):
    char_id = ndb.StringProperty(required=True)
    corp_name = ndb.StringProperty()


class AppEngineTaskletTestCase(GAETestCase):

    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_urlfetch_stub()
        
        self.char = EveChar(char_id='1234')
        self.char.put()

        self.test_xml = r"""
            <?xml version='1.0' encoding='UTF-8'?>
            <eveapi version="2">
                <currentTime>2009-10-18 17:05:31</currentTime>
                <result>
                    <characterID>1234</characterID>
                    <characterName>Test1 Character</characterName>
                    <race>Caldari</race>
                    <bloodline>Civire</bloodline>
                    <corporationID>2345</corporationID>
                    <corporation>Test1 Corporation</corporation>
                    <corporationDate>2012-06-03 02:10:00</corporationDate>
                    <securityStatus>2.50000000000000</securityStatus>
                    <rowset name="employmentHistory">
                        <row corporationID="1" startDate="2012-06-02 02:10:00" />
                        <row corporationID="2" startDate="2011-10-12 12:34:56" />
                    </rowset>
                </result>
                <cachedUntil>2009-11-18 17:05:31</cachedUntil>
            </eveapi>
        """.strip()

        # mock urlrfetch service
        # see http://stackoverflow.com/questions/9943996/how-to-mock-ndb-get-context-urlfetch
        uf = self.testbed.get_stub('urlfetch')
        uf._Dynamic_Fetch = mock.Mock()

    def tearDown(self):
        self.testbed.deactivate()

    @mock.patch('google.appengine.api.urlfetch.urlfetch_service_pb.URLFetchResponse')
    def testAsyncIteration(self, URLFetchResponse):
        api = appengine.AppEngineAPI()
        client = eve.EVE(api=api)

        # mocking rpc response object
        response = URLFetchResponse.return_value
        response.contentwastruncated.return_value = False
        response.statuscode.return_value = 200
        response.content.return_value = self.test_xml

        @ndb.tasklet
        def get_info_async(char):
            api_result = yield api.get_async(
                'eve/CharacterInfo',
                {'characterID': char.char_id}
            )
            result = client.character_info_from_id(
                char.char_id,
                api_result=api_result
            )
            
            if result:
                char.corp_name = result['corp']['name']
                yield char.put_async()

            raise ndb.Return(char)
        
        char = get_info_async(self.char).get_result()
        self.assertEqual(char, self.char)
        self.assertEqual('Test1 Corporation', char.key.get().corp_name)


if __name__ == "__main__":
    unittest.main()
