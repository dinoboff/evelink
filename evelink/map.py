from evelink import api

class Map(object):
    """Wrapper around /map/ of the EVE API."""

    @api.auto_api
    def __init__(self, api=None):
        self.api = api

    def jumps_by_system(self, api_result=None):
        """Get jump counts for systems in the last hour.

        Returns a tuple of ({system:jumps...}, timestamp).

        NOTE: Systems with 0 jumps in the last hour are not included!
        """

        if api_result is None:
            api_result = self.api.get('map/Jumps')

        rowset = api_result.result.find('rowset')
        results = {}
        for row in rowset.findall('row'):
            system = int(row.attrib['solarSystemID'])
            jumps = int(row.attrib['shipJumps'])
            results[system] = jumps

        data_time = api.parse_ts(api_result.result.find('dataTime').text)

        return api.APIResult((results, data_time), api_result.timestamp, api_result.expires)

    def kills_by_system(self, api_result=None):
        """Get kill counts for systems in the last hour.

        Returns a tuple of ({system:{killdata}, timestamp).

        Each {killdata} is {'faction':count, 'ship':count, 'pod':count}.
        """

        if api_result is None:
            api_result = self.api.get('map/Kills')

        rowset = api_result.result.find('rowset')
        results = {}
        for row in rowset.findall('row'):
            system = int(row.attrib['solarSystemID'])
            faction_kills = int(row.attrib['factionKills'])
            ship_kills = int(row.attrib['shipKills'])
            pod_kills = int(row.attrib['podKills'])

            results[system] = {
                'id': system,
                'faction': faction_kills,
                'ship': ship_kills,
                'pod': pod_kills,
            }

        data_time = api.parse_ts(api_result.result.find('dataTime').text)

        return api.APIResult((results, data_time), api_result.timestamp, api_result.expires)

    def faction_warfare_systems(self, api_result=None):
        """Get a dict of factional warfare systems and their info."""

        if api_result is None:
            api_result = self.api.get('map/FacWarSystems')

        rowset = api_result.result.find('rowset')
        results = {}
        for row in rowset.findall('row'):
            system = int(row.attrib['solarSystemID'])
            name = row.attrib['solarSystemName']
            faction_id = int(row.attrib['occupyingFactionID']) or None
            faction_name = row.attrib['occupyingFactionName'] or None
            contested = (row.attrib['contested'] == 'True')

            results[system] = {
                'id': system,
                'name': name,
                'faction': {
                    'id': faction_id,
                    'name': faction_name,
                },
                'contested': contested,
            }

        return api.APIResult(results, api_result.timestamp, api_result.expires)

    def sov_by_system(self, api_result=None):
        """Get sovereignty info keyed by system."""

        if api_result is None:
            api_result = self.api.get('map/Sovereignty')

        rowset = api_result.result.find('rowset')
        results = {}
        for row in rowset.findall('row'):
            system = int(row.attrib['solarSystemID'])
            name = row.attrib['solarSystemName']
            faction_id = int(row.attrib['factionID']) or None
            alliance_id = int(row.attrib['allianceID']) or None
            corp_id = int(row.attrib['corporationID']) or None

            results[system] = {
                'id': system,
                'name': name,
                'faction_id': faction_id,
                'alliance_id': alliance_id,
                'corp_id': corp_id,
            }

        data_time = api.parse_ts(api_result.result.find('dataTime').text)

        return api.APIResult((results, data_time), api_result.timestamp, api_result.expires)
