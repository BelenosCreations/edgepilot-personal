"""Configuration-only risk and isolation checks for all three EdgePilot engines."""
import os
import tempfile
import unittest
from engine import engine_config


class EngineConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.temp.name,'plans.db')
        engine_config.setup(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_distinct_profiles_start_inactive_and_empty(self):
        profiles=engine_config.all_profiles(self.path)
        self.assertEqual(set(profiles),{'auto','micro','fifteen'})
        for name,p in profiles.items():
            with self.subTest(engine=name):
                self.assertFalse(p['active'])
                self.assertFalse(p['liveTradingAvailable'])
                self.assertFalse(p['paperTradingAvailable'])
                self.assertFalse(p['configured'])
                self.assertEqual(p['mode'],'configuration_only')

    def test_configuration_survives_and_does_not_touch_other_engines(self):
        plan=engine_config.DEFAULTS['micro'].copy()
        plan.update({'allocation':'20.00','max_per_trade':'2.00','loss_stop':'5.00',
                     'profit_target':'10.00','max_trades':10,'max_open':1})
        saved=engine_config.save(self.path,'micro',plan)
        self.assertTrue(saved['configured'])
        self.assertEqual(saved['config']['allocation'],'20.00')
        self.assertEqual(saved['config']['loss_stop'],'5.00')
        self.assertEqual(engine_config.read(self.path,'micro')['config']['max_trades'],10)
        self.assertFalse(engine_config.read(self.path,'auto')['configured'])
        self.assertFalse(engine_config.read(self.path,'fifteen')['configured'])
        self.assertFalse(saved['active'])

    def test_invalid_settings_and_trade_activation_are_rejected(self):
        plan=engine_config.DEFAULTS['micro'].copy()
        for key,value in [
            ('allocation','-1'),('allocation','NaN'),('max_trades',0),
            ('max_trades',101),('max_open',0),('stock_market','yes'),
            ('max_per_trade','0.001'),('cooldown_seconds',-1)]:
            with self.subTest(key=key,value=value):
                changed=plan.copy();changed[key]=value
                with self.assertRaises(ValueError):
                    engine_config.save(self.path,'micro',changed)
        bad=plan.copy();bad['active']=True
        with self.assertRaisesRegex(ValueError,'activation is unavailable'):
            engine_config.save(self.path,'micro',bad)
        self.assertFalse(engine_config.read(self.path,'micro')['configured'])

    def test_per_trade_and_loss_stop_cannot_exceed_allocation(self):
        plan=engine_config.DEFAULTS['micro'].copy()
        plan.update({'allocation':'5.00','max_per_trade':'6.00'})
        with self.assertRaisesRegex(ValueError,'per-trade'):
            engine_config.validate('micro',plan)
        plan.update({'max_per_trade':'2.00','loss_stop':'6.00'})
        with self.assertRaisesRegex(ValueError,'Loss stop'):
            engine_config.validate('micro',plan)

    def test_auto_trading_is_separate_from_micro_and_fifteen(self):
        plan=engine_config.DEFAULTS['auto'].copy()
        plan.update({'stock_allocation':'20.00','crypto_allocation':'10.00',
                     'max_per_trade':'5.00','loss_stop':'4.00'})
        engine_config.save(self.path,'auto',plan)
        self.assertEqual(engine_config.read(self.path,'auto')['config']['crypto_allocation'],'10.00')
        self.assertEqual(engine_config.read(self.path,'micro')['config']['allocation'],'0.00')

    def test_fifteen_expiry_range_and_market_filters(self):
        plan=engine_config.DEFAULTS['fifteen'].copy()
        plan.update({'minimum_seconds_left':150,'max_spread_pct':'3.00'})
        self.assertEqual(engine_config.save(self.path,'fifteen',plan)['config']['minimum_seconds_left'],150)
        plan['minimum_seconds_left']=899
        with self.assertRaises(ValueError):
            engine_config.save(self.path,'fifteen',plan)
        with self.assertRaisesRegex(ValueError,'Unknown EdgePilot engine'):
            engine_config.read(self.path,'fake')


if __name__=='__main__':
    unittest.main()
