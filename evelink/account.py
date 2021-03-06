from evelink import api
from evelink import constants

class Account(object):
    """Wrapper around /account/ of the EVE API.

    Note that a valid API key is required.
    """

    def __init__(self, api):
        self.api = api

    def status(self, api_result=None):
        """Returns the account's subscription status."""
        if api_result is None:
            api_result = self.api.get('account/AccountStatus')

        _str, _int, _float, _bool, _ts = api.elem_getters(api_result.result)

        result = {
            'paid_ts': _ts('paidUntil'),
            'create_ts': _ts('createDate'),
            'logins': _int('logonCount'),
            'minutes_played': _int('logonMinutes'),
        }

        return api.APIResult(result, api_result.timestamp, api_result.expires)

    def key_info(self, api_result=None):
        """Returns the details of the API key being used to auth."""

        if api_result is None:
            api_result = self.api.get('account/APIKeyInfo')

        key = api_result.result.find('key')
        result = {
            'access_mask': int(key.attrib['accessMask']),
            'type': constants.APIKey.key_types[key.attrib['type']],
            'expire_ts': api.parse_ts(key.attrib['expires']) if key.attrib['expires'] else None,
            'characters': {},
        }

        rowset = key.find('rowset')
        for row in rowset.findall('row'):
            character = {
                'id': int(row.attrib['characterID']),
                'name': row.attrib['characterName'],
                'corp': {
                    'id': int(row.attrib['corporationID']),
                    'name': row.attrib['corporationName'],
                },
            }
            result['characters'][character['id']] = character

        return api.APIResult(result, api_result.timestamp, api_result.expires)

    def characters(self, api_result=None):
        """Returns all of the characters on an account."""

        if api_result is None:
            api_result = self.api.get('account/Characters')

        rowset = api_result.result.find('rowset')
        result = {}
        for row in rowset.findall('row'):
            character = {
                'id': int(row.attrib['characterID']),
                'name': row.attrib['name'],
                'corp': {
                    'id': int(row.attrib['corporationID']),
                    'name': row.attrib['corporationName'],
                },
            }
            result[character['id']] = character

        return api.APIResult(result, api_result.timestamp, api_result.expires)
