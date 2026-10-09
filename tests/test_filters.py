import unittest
from datetime import date, timedelta
from unittest.mock import Mock
from koiene import (Cabin, DayAvailability, KoieneClient, by_difficulty, by_price,
                    by_walking_time, by_public_transport_time, available_stays)


class FilteringTests(unittest.TestCase):
    def test_strict_time_boundaries_and_unknowns(self):
        cabins = [Cabin(str(n), '', difficulty=n, public_transport_min=t,
                        walking_time_winter_min=t) for n,t in [(0,0),(2,179),(4,180),(5,181)]]
        self.assertEqual([c.name for c in by_difficulty(cabins,4)], ['2','4'])
        self.assertEqual([c.name for c in by_public_transport_time(cabins,180,strict=True)], ['2'])
        self.assertEqual([c.name for c in by_public_transport_time(cabins,180)], ['2','4'])
        self.assertEqual([c.name for c in by_walking_time(cabins,180,summer=False)], ['2','4'])
        self.assertEqual(by_price([Cabin('unknown','')],100), [])

    def test_consecutive_nights_gaps_and_unreleased(self):
        c=Cabin('test','',capacity=4,dates=[
            DayAvailability('2026-10-09',4,4,True,'available'),
            DayAvailability('2026-10-10',2,2,True,'available'),
            DayAvailability('2026-10-12',4,4,True,'available'),
            DayAvailability('2026-10-16',None,4,False,'not_yet_open'),
            DayAvailability('2026-10-17',None,4,False,'not_yet_open'),
        ])
        stays=available_stays(c,nights=2,weekend=True,min_beds=2)
        self.assertEqual(len(stays),1)
        self.assertEqual(stays[0]['check_out'],'2026-10-11')
        self.assertEqual(stays[0]['min_beds'],2)
        self.assertEqual(available_stays(c,nights=2,whole_cabin=True),[])
        tentative=available_stays(c,nights=2,weekend=True,whole_cabin=True,include_unreleased=True)
        self.assertEqual(tentative,[{'check_in':'2026-10-16','check_out':'2026-10-18','min_beds':4,'booking_open':False}])
        self.assertEqual(available_stays(c,nights=3),[])
        unknown=Cabin('unknown','',dates=[DayAvailability('2026-10-09',None,4,None,'unknown')])
        self.assertEqual(available_stays(unknown,include_unreleased=True),[])

    def test_inventory_states(self):
        sources=['aap=ja&led=3&kap=4','aap=ja&typ=Full','aap=ja&typ=Opptatt',
                 'aap=nei&led=4&kap=4','aap=nei&typ=Opptatt','aap=ja&led=invalid','aap=ja&led=0']
        cells=''.join(f'<td><a href="detail.php?d=2026-10-{9+i:02}"><img src="rutevisning.php?{src}"></a></td>' for i,src in enumerate(sources))
        session=Mock();session.headers={}
        session.get.return_value.text=f'<table cellpadding="0"><tr><td><a href="https://example.com?k=test">Test</a></td>{cells}</tr></table>'
        client=KoieneClient(session);cabins={};client._fetch_overview_window('2026-10-09',cabins)
        days=cabins['Test'].dates
        self.assertEqual([d.status for d in days],['available','full','reserved','not_yet_open','reserved','unknown','full'])
        self.assertEqual([d.available_beds for d in days],[3,0,0,None,None,None,0])
        self.assertEqual(days[3].listed_beds,4)
        self.assertFalse(days[3].booking_open)

    def test_missing_table_is_an_error(self):
        session=Mock();session.headers={};session.get.return_value.text='<html>Unavailable</html>'
        with self.assertRaises(ValueError):
            KoieneClient(session)._fetch_overview_window('2026-10-09',{})

    def test_range_windows_and_completeness(self):
        client=KoieneClient();client._fetch_matrix=Mock(return_value={});client._enrich_prices=Mock()
        starts=[]
        def fill(start,cabins):
            starts.append(start)
            c=cabins.setdefault('Test',Cabin('Test',''))
            c.dates.extend(DayAvailability((date.fromisoformat(start)+timedelta(days=i)).isoformat(),1,1,True,'available') for i in range(7))
        client._fetch_overview_window=fill
        cabins=client.fetch_range('2026-10-09','2026-10-24')
        self.assertEqual(starts,['2026-10-09','2026-10-16','2026-10-23'])
        self.assertEqual(len(cabins[0].dates),16)
        with self.assertRaises(ValueError):client.fetch_range('2026-10-10','2026-10-09')
        def incomplete(start,cabins):
            cabins['Test']=Cabin('Test','',dates=[DayAvailability(start)])
        client._fetch_overview_window=incomplete
        with self.assertRaises(ValueError):client.fetch_range('2026-10-09','2026-10-10')


if __name__=='__main__':unittest.main()
