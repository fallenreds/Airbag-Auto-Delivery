import threading
import time
import logging

logger = logging.getLogger(__name__)


class GoodsCacheService:
    def __init__(self, crm_client, warehouse, categories_ignore_ids, update_interval=20):
        self.crm_client = crm_client
        self.warehouse = warehouse
        self.categories_ignore_ids = categories_ignore_ids
        self.update_interval = update_interval
        self.goods = {"data": []}
        self.run_thread = threading.Thread(target=self._update_goods_loop)
        self.run_thread.daemon = True
        self.run_thread.start()

    def _update_goods_loop(self):
        while True:
            try:
                goods = self.crm_client.get_all_goods(self.warehouse)
                filtered_goods = filter(lambda x: x['category']["id"] not in self.categories_ignore_ids, goods)
                self.goods = {"data": list(filtered_goods)}
                logger.info('Goods updated')
            except Exception as error:
                logger.error('Error updating goods: %s', error)

            # Wait for the next update
            time.sleep(self.update_interval)

    def get_goods(self):
        return self.goods