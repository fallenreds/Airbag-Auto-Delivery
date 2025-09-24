import unittest

from django.conf import settings
from django.test import TestCase

from core.services.remonline.api import RemonlineInterface


class TestRemonlineAPI(TestCase):
    test_ids = [
        55954121,
        55954117,
        55953780,
        55952688,
        55952687,
        55951388,
        55950423,
        55950356,
        55949933,
        55949907,
        55949821,
        55949620,
        55948999,
        55945878,
        55945488,
        55940891,
        55940242,
        55940177,
        55939210,
        55937812,
        55937776,
        55936636,
        55935936,
        55935524,
        55935103,
        55934848,
        55934380,
        55934347,
        55934283,
        55934257,
        55916573,
        55916562,
        55916560,
        55916038,
        55915396,
        55914518,
        55913220,
        55912047,
        55911643,
        55911451,
        55908077,
        55908000,
        55907705,
        55907535,
        55905774,
        55905445,
        55905274,
        55905187,
        55904994,
        55904693,
        55904646,
        55904597,
        55904564,
        55903269,
        55902051,
        55898393,
        55897075,
        55894434,
        55883370,
        55879465,
        55875342,
        55873055,
        55872105,
        55871197,
        55870927,
        55870816,
        55870733,
        55870672,
        55870562,
        55870504,
        55870315,
        55870251,
        55870201,
        55869224,
        55865670,
        55860687,
        55859532,
        55855530,
        55849275,
        55848722,
        55848623,
        55845679,
        55838451,
        55833929,
        55826008,
        55825075,
        55824781,
        55822934,
        55822535,
        55821556,
        55821496,
        55821413,
        55821203,
        55820673,
        55817304,
        55811295,
        55807628,
        55800006,
        55799955,
        55799949,
        55799948,
        55799842,
        55794729,
        55792245,
        55790940,
        55789735,
        55789681,
        55789619,
        55789579,
        55788175,
        55783673,
        55780488,
        55780441,
        55770705,
        55769949,
        55769704,
        55769155,
        55768171,
        55768117,
        55764678,
        55764566,
        55764288,
        55763509,
        55763434,
        55760240,
        55759846,
        55759771,
        55759660,
        55758802,
        55754661,
        55754449,
        55750499,
        55748815,
        55745222,
        55744818,
        55742987,
        55741801,
        55741785,
        55736302,
        55729083,
        55720578,
        55720122,
        55717866,
        55717760,
        55717701,
        55717681,
        55716026,
        55715203,
        55714350,
        55714201,
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_key = settings.REMONLINE_API_KEY
        if not cls.api_key:
            raise unittest.SkipTest("REMONLINE_API_KEY not found in settings")

        cls.remonline = RemonlineInterface(cls.api_key)

    @classmethod
    def tearDownClass(cls):
        pass

    def test_get_orders_by_ids(self):
        # Test with 150 orders as requested
        # 150 orders for testing

        # Call the method with real API
        result = self.remonline.get_orders_by_ids(self.test_ids)

        # Basic assertions
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 0)  # At least 0 orders returned

        # Extract IDs from the result and compare with test_ids
        result_ids = [order["id"] for order in result]
        self.assertCountEqual(result_ids, self.test_ids)

        # Check structure of returned orders
        for order in result:
            self.assertIn("id", order)
            self.assertIn("status", order)
            self.assertIn("id", order["status"])
            self.assertIn("name", order["status"])

            # Log some info about the order for debugging
            print(f"Order ID: {order['id']}, Status: {order['status']['name']}")


if __name__ == "__main__":
    unittest.main()
