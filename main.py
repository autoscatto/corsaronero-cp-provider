from bs4 import BeautifulSoup
from couchpotato.core.helpers.encoding import simplifyString, tryUrlencode
from couchpotato.core.helpers.variable import tryInt
from couchpotato.core.logger import CPLog
from couchpotato.core.providers.torrent.base import TorrentMagnetProvider
import datetime
import traceback
import re

log = CPLog(__name__)


class CorsaroNero(TorrentMagnetProvider):
    urls = {
        'test': 'http://ilcorsaronero.info',
        'base_url': 'http://ilcorsaronero.info',
        'detail': 'http://ilcorsaronero.info/tor/%d/%s',
        'search': 'http://ilcorsaronero.info/torrent-ita/%d/%s.html',
    }

    ### TODO: are animated movies released to DVDrip or Anime category? ###
    cat_ids = [
        (1, 'DVDrip'),
        # (5, 'Anime'),
    ]

    http_time_between_calls = 1  # seconds
    cat_backup_id = None

    ### TODO: what about movie year and quality? ###
    def _searchOnTitle(self, title, movie, quality, results):
        log.debug("Searching for %s (imdb: %s) (%s) on %s" % (title,
                                                              movie['library']['identifier'].replace('tt', ''),
                                                              quality['label'],
                                                              self.urls['base_url']))

        # Get italian title
        # First, check cache
        cache_key = 'italiantitle.%s' % movie['library']['identifier']
        italiantitle = self.getCache(cache_key)

        if not italiantitle:
            try:
                dataimdb = self.getHTMLData(
                    'http://www.imdb.com/title/%s/releaseinfo' % (movie['library']['identifier']))
                html = BeautifulSoup(dataimdb)
                titletable = html.find("table", id='akas')
                try:
                    italiantitle = html.find('table', id='akas').find('td', text="Italy").findNext().text
                except:
                    log.debug(
                        'Failed to find italian title for %s, it has probably never been released in Italy, '
                        'we\'ll try searching for the original title anyways',
                        title)
                    italiantitle = title
            except:
                log.error('Failed parsing iMDB for italian title, using the original one: %s', traceback.format_exc())
                italiantitle = title

            self.setCache(cache_key, italiantitle, timeout=25920000)

        log.debug("Title after searching for the italian one: %s" % italiantitle)

        # remove accents
        simpletitle = simplifyString(italiantitle)
        data = self.getHTMLData(self.urls['search'] % (1, tryUrlencode(simpletitle)))

        if 'Nessus torrent trovato!!!!' in data:
            log.info("No torrents found for %s on ilCorsaroNero.info.", italiantitle)
            return

        if data:
            try:
                html = BeautifulSoup(data)
                entries_1 = html.findAll('tr', attrs={'class': re.compile(r'odd?')})
                try:
                    self.parseResults(results, entries_1)

                except:
                    log.error('Failed parsing ilCorsaroNero: %s', traceback.format_exc())

            except AttributeError:
                log.debug('No search results found.')

    # computes days since the torrent release
    def ageToDays(self, age_str):
        # actually a datetime.timedelta object
        tdelta = datetime.datetime.now() - datetime.datetime.strptime(age_str, "%d.%m.%y")
        # to int
        return tdelta.days

    # retrieves the magnet link from the detail page of the original torrent result
    def getMagnetLink(self, url):
        data = self.getHTMLData(url)
        html = BeautifulSoup(data)
        magnet = html.find('a', attrs={'class': 'forbtn'})['href']
        return magnet

    # filters the <td> elements containing the results, if any
    def parseResults(self, results, entries):
        for result in entries:
            new = {}
            try:
                res = [t.text if t.text != "" else t.a.get('href') for t in result.findAll('td')]
            except:
                log.info("Wrong search result format, skipping.")
                continue

            if len(res) != 7:
                log.info("Wrong search result format, skipping.")
                #print res
                continue

            if res[0] != self.cat_ids[0][1]:  # or cat == self.cat_ids[1][1]:
                log.info("Wrong category: %s not a movie, skipping.", res[0])
                continue

            log.info("Hit right category: %s is a movie, keep going.", (res[0]))
            try:
                # res format: [category, rel title, size, rel url, date, seeders, leechers]

                # extract the title from the real link instead of the text
                # because the text is often cut and doesn't contain the full release name
                #new['name'] = res[2].split('/')[5]
                new['name'] = res[1]
                new['size'] = self.parseSize(res[2])
                new['detail_url'] = res[3]
                new['id'] = new['detail_url'].split('/')[4]
                new['url'] = self.getMagnetLink(new['detail_url'])
                new['age'] = self.ageToDays(res[4])
                new['seeders'] = tryInt(res[5])
                new['leechers'] = tryInt(res[6])
                ### TODO: what about score extras here ??? ###
                new['score'] = 0
            except Exception, e:
                log.info("Search entry processing FAILED!")
                print e
                continue

            results.append(new)
            log.debug("New result %s", new)
