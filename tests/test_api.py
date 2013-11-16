from StringIO import StringIO
import unittest2 as unittest

import mock

import evelink.api as evelink_api

class HelperTestCase(unittest.TestCase):

    def test_parse_ts(self):
        self.assertEqual(
            evelink_api.parse_ts("2012-06-12 12:04:33"),
            1339502673,
        )


class CacheTestCase(unittest.TestCase):

    def setUp(self):
        self.cache = evelink_api.APICache()

    def test_cache(self):
        self.cache.put('foo', 'bar', 3600)
        self.assertEqual(self.cache.get('foo'), 'bar')

    def test_expire(self):
        self.cache.put('baz', 'qux', -1)
        self.assertEqual(self.cache.get('baz'), None)


class APIRequestTest(unittest.TestCase):

    def setUp(self):
        self.api = mock.Mock()
        self.api.CACHE_VERSION = 1
        self.api.base_url = 'api.eveonline.com'
        self.api.api_key = None


    def test_request_eq(self):
        self.assertEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {}),
            evelink_api.APIRequest(self.api, 'foo/bar', {})
        )
        self.assertEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {})),
            str(evelink_api.APIRequest(self.api, 'foo/bar', {}))
        )

        self.assertEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1, 'b': 2}),
            evelink_api.APIRequest(self.api, 'foo/bar', {'b': 2, 'a': 1})
        )
        self.assertEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1, 'b': 2})),
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'b': 2, 'a': 1}))
        )

    def test_request_with_api_key_eq(self):
        self.api.api_key = (1, 'code',)
        self.assertEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {}),
            evelink_api.APIRequest(self.api, 'foo/bar', {})
        )

        self.assertEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {})),
            str(evelink_api.APIRequest(self.api, 'foo/bar', {}))
        )

    def test_request_not_eq(self):
        self.assertNotEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {}),
            evelink_api.APIRequest(self.api, 'foo/baz', {})
        )
        self.assertNotEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {})),
            str(evelink_api.APIRequest(self.api, 'foo/baz', {}))
        )

        self.assertNotEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1}),
            evelink_api.APIRequest(self.api, 'foo/bar', {'a': 2})
        )
        self.assertNotEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1})),
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'a': 2}))
        )

        self.assertNotEqual(
            evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1}),
            evelink_api.APIRequest(self.api, 'foo/bar', {'b': 1})
        )
        self.assertNotEqual(
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1})),
            str(evelink_api.APIRequest(self.api, 'foo/bar', {'b': 1}))
        )

    def test_request_with_api_key_not_eq(self):
        self.api.api_key = (1, 'code',)
        req1 = evelink_api.APIRequest(self.api, 'foo/bar', {})

        self.api.api_key = (2, 'code',)
        req2 = evelink_api.APIRequest(self.api, 'foo/bar', {})


        self.assertNotEqual(req1, req2)
        self.assertNotEqual(str(req1), str(req2))

    @unittest.skip("base url not part of the cache key hash")
    def test_variance_on_base_url(self):
        req1 = evelink_api.APIRequest(self.api, 'foo/bar', {})
        self.api.base_url = 'api.testeveonline.com'
        req2 = evelink_api.APIRequest(self.api, 'foo/bar', {})

        self.assertNotEqual(req1, req2)
        self.assertNotEqual(str(req1), str(req2))

    def test_str(self):
        req = evelink_api.APIRequest(self.api, 'foo/bar', {'a': 1, 'b': 2})
        self.assertEqual(
            '1-%s' % hash(('foo/bar', (('a', '1'), ('b', '2')),)),
            str(req)
        )



class APITestCase(unittest.TestCase):

    def setUp(self):
        self.cache = mock.MagicMock(spec=evelink_api.APICache)
        self.api = evelink_api.API(cache=self.cache)

        # force disable requests if enabled.
        self.api.Request = evelink_api.APIRequest

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

        self.error_xml = r"""
                <?xml version='1.0' encoding='UTF-8'?>
                <eveapi version="2">
                    <currentTime>2009-10-18 17:05:31</currentTime>
                    <error code="123">
                        Test error message.
                    </error>
                    <cachedUntil>2009-11-18 19:05:31</cachedUntil>
                </eveapi>
            """.strip()

    @mock.patch('urllib2.urlopen')
    def test_get(self, mock_urlopen):
        # mock up an urlopen compatible response object and pretend to have no
        # cached results; similar pattern for all test_get_* methods below.
        mock_urlopen.return_value = StringIO(self.test_xml)
        self.cache.get.return_value = None

        result = self.api.get('foo/Bar', {'a':[1,2,3]})

        rowset = result.find('rowset')
        rows = rowset.findall('row')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].attrib['foo'], 'bar')
        self.assertEqual(self.api.last_timestamps, {
            'current_time': 1255885531,
            'cached_until': 1258563931,
        })

    @mock.patch('urllib2.urlopen')
    def test_cached_get(self, mock_urlopen):
        """Make sure that we don't try to call the API if the result is cached."""
        # mock up a urlopen compatible error response, and pretend to have a
        # good test response cached.
        mock_urlopen.return_value = StringIO(self.error_xml)
        self.cache.get.return_value = self.test_xml

        result = self.api.get('foo/Bar', {'a':[1,2,3]})

        # Ensure this is really not called.
        self.assertFalse(mock_urlopen.called)

        rowset = result.find('rowset')
        rows = rowset.findall('row')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].attrib['foo'], 'bar')

        # timestamp attempted to be extracted.
        self.assertEqual(self.api.last_timestamps, {
            'current_time': 1255885531,
            'cached_until': 1258563931,
        })

    @mock.patch('urllib2.urlopen')
    def test_get_with_apikey(self, mock_urlopen):
        mock_urlopen.return_value = StringIO(self.test_xml)
        self.cache.get.return_value = None

        self.api.api_key = (1, 'code')

        self.api.get('foo', {'a':[2,3,4]})

        # Make sure the api key id and verification code were passed
        self.assertEqual(mock_urlopen.mock_calls, [
                mock.call(
                    'https://api.eveonline.com/foo.xml.aspx',
                    'a=2%2C3%2C4&keyID=1&vCode=code',
                ),
            ])

    @mock.patch('urllib2.urlopen')
    def test_get_with_error(self, mock_urlopen):
        mock_urlopen.return_value = StringIO(self.error_xml)
        self.cache.get.return_value = None

        self.assertRaises(evelink_api.APIError,
            self.api.get, 'eve/Error')
        self.assertEqual(self.api.last_timestamps, {
            'current_time': 1255885531,
            'cached_until': 1258571131,
        })

    @mock.patch('urllib2.urlopen')
    def test_cached_get_with_error(self, mock_urlopen):
        """Make sure that we don't try to call the API if the result is cached."""
        # mocked response is good now, with the error response cached.
        mock_urlopen.return_value = StringIO(self.test_xml)
        self.cache.get.return_value = self.error_xml

        self.assertRaises(evelink_api.APIError,
            self.api.get, 'foo/Bar', {'a':[1,2,3]})

        self.assertFalse(mock_urlopen.called)
        self.assertEqual(self.api.last_timestamps, {
            'current_time': 1255885531,
            'cached_until': 1258571131,
        })


if __name__ == "__main__":
    unittest.main()
