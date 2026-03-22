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
        self._last_goods_count: int | None = None
        self._update_cycle = 0
        self.run_thread = threading.Thread(target=self._update_goods_loop)
        self.run_thread.daemon = True
        self.run_thread.start()

    def _update_goods_loop(self):
        while True:
            self._update_cycle += 1
            try:
                goods = self.crm_client.get_all_goods(self.warehouse)
                filtered_goods = filter(lambda x: x['category']["id"] not in self.categories_ignore_ids, goods)
                filtered_goods_list = list(filtered_goods)
                current_count = len(filtered_goods_list)
                self.goods = {"data": filtered_goods_list}

                if self._last_goods_count is None:
                    logger.info(
                        "goods_cache_initialized goods_count=%s update_interval_sec=%s",
                        current_count,
                        self.update_interval,
                    )
                elif self._last_goods_count != current_count:
                    logger.info(
                        "goods_cache_size_changed previous_count=%s current_count=%s cycle=%s",
                        self._last_goods_count,
                        current_count,
                        self._update_cycle,
                    )
                else:
                    logger.debug(
                        "goods_cache_refreshed goods_count=%s cycle=%s",
                        current_count,
                        self._update_cycle,
                    )

                self._last_goods_count = current_count
            except Exception:
                logger.exception('goods_cache_update_failed')

            # Wait for the next update
            time.sleep(self.update_interval)

    def get_goods(self):
        return self.goods
