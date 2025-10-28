import ast
import json
import logging
import sqlite3

from models import BaseTemplate, Template, BaseClientUpdate, ClientUpdate


class DBConnection:
    def __init__(self, dbpath):
        self.connection = sqlite3.connect(dbpath)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.cursor.row_factory = self.dict_factory

    @staticmethod
    def dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    #--------------- Client Updates -------------- #
    def get_client_updates(self) -> list[ClientUpdate]:
        self.cursor.execute(f"""select * from client_updates""")
        return [ClientUpdate(**data) for data in self.cursor.fetchall()]

    def get_client_update(self, client_update_id: int) -> ClientUpdate|None:
        self.cursor.execute(f"""select * from client_updates where id=?""", (client_update_id,))
        result = self.cursor.fetchone()
        return ClientUpdate(**result) if result else None


    def delete_client_update(self, client_update_id: int) -> None:
        self.cursor.execute(f"""delete from client_updates where id=?""", (client_update_id,))
        self.connection.commit()
        return None

    def create_client_update(self, client_updates: BaseClientUpdate) -> ClientUpdate:
        """Create new template"""
        self.cursor.execute(f"""insert into client_updates ('type', 'client_id') values (?,?)""", (client_updates.type, client_updates.client_id))
        self.connection.commit()
        return self.get_client_update(self.cursor.lastrowid)

    #--------------- END.Client Updates -------------- #


    #--------------- TEMPLATES -------------- #

    def get_templates(self) -> list[Template]:
        self.cursor.execute(f"""select * from template""")
        return [Template(**data) for data in self.cursor.fetchall()]

    def get_template(self, template_id: int) -> Template|None:
        self.cursor.execute(f"""select * from template where id=?""", (template_id,))
        result = self.cursor.fetchone()
        return Template(**result) if result else None


    def delete_template(self, template_id: int) -> None:
        self.cursor.execute(f"""delete from template where id=?""", (template_id,))
        self.connection.commit()
        return None

    def create_template(self, template: BaseTemplate) -> Template:
        """Create new template"""
        self.cursor.execute(f"""insert into template ('name', 'text') values (?,?)""", (template.name,template.text))
        self.connection.commit()
        return self.get_template(self.cursor.lastrowid)
    #--------------- END. TEMPLATES -------------- #

    # visitors methods
    def get_visitor_by_tg(self, telegram_id):
        self.cursor.execute("""select * from visitors where telegram_id=?""", (telegram_id,))
        return self.cursor.fetchone()

    def get_visitors(self):

        self.cursor.execute(f"""select * from visitors""")
        return self.cursor.fetchall()
    def delete_visitor(self, telegram_id:int):
        self.cursor.execute("""delete from visitors where telegram_id=?""", (telegram_id,))

        self.connection.commit()


    def post_new_visitor(self, telegram_id):
        response = {"success": True, "data": None}
        print(self.get_visitor_by_tg(telegram_id))
        try:
            if not self.get_visitor_by_tg(telegram_id):
                self.cursor.execute(f""" 
                            insert into visitors ('telegram_id')
                            values(?)""", (telegram_id,))
                self.connection.commit()
                response = {"success": True, "data": "New visitor has successfully created"}
            else:
                response = {"success": True, "data": "New visitor has NOT successfully created"}
        except Exception as error:
            print(error)
            response = {"success": False, "data": error}
        finally:
            return response

    # shopping cart methods
    def list_shopping_cart(self, telegram_id=None):
        telegram_filter = ""
        if telegram_id:
            telegram_filter = "where telegram_id = {0}".format(telegram_id)

        self.cursor.execute("select * from shopping_cart {0} ".format(telegram_filter))
        data = [dict(ix) for ix in self.cursor.fetchall()]
        return data

    def update_shopping_cart_count(self, cart_id, count):
        self.cursor.execute("""
               update shopping_cart
               set 'count' = {0}
               where id = {1} 
               """.format(count, cart_id))
        self.connection.commit()

    def delete_shopping_cart(self, cart_id):
        self.cursor.execute(f"""
               delete from shopping_cart
               where id=(?); """, (cart_id,))
        self.connection.commit()

    def post_shopping_cart(self, telegram_id: int, good_id: int, count: int = 1):
        self.cursor.execute(f""" 
               insert into shopping_cart ('telegram_id', 'good_id', 'count')
               values(?,?,?)""", (telegram_id, good_id, count))
        self.connection.commit()

    # client methods
    def get_client_by_login(self, login: str):
        self.cursor.execute(f"""
        select * from client where login=?
        """, (login,))
        return self.cursor.fetchone()

    def get_client_by_phone(self, phone: str):
        self.cursor.execute(f"""
        select * from client where phone=?
        """, (phone,))
        return self.cursor.fetchone()

    def get_all_clients(self):
        self.cursor.execute(
            """select * from client"""
        )
        return self.cursor.fetchall()

    def get_client_by_telegram_id(self, telegram_id):
        self.cursor.execute("""
            select * from client
            where telegram_id = {0}
        """.format(telegram_id))
        return self.cursor.fetchone()

    def get_client_by_id(self, client_id):
        self.cursor.execute("""
            select * from client
            where id= {0}
        """.format(client_id))
        return self.cursor.fetchone()



    def update_client_telegram_id(self, client_id, new_id):

        self.cursor.execute(
            """
            update client
            set telegram_id = {0}
            where id = {1} 
            """.format(new_id, client_id)

        )

        self.connection.commit()

    def post_client(self,
                    id_remonline,
                    telegram_id,
                    name,
                    last_name,
                    login,
                    password,
                    phone
                    ):
        self.cursor.execute(f"""
                    insert into client 
                        (id_remonline,
                        telegram_id,
                        'name',
                        last_name,
                        login,
                        password,
                        phone
                         )

                    values (?,?,?,?,?,?,?)""", (
            id_remonline,
            telegram_id,
            name,
            last_name,
            login,
            password,
            phone)

                            )

        self.connection.commit()

        return self.cursor.lastrowid

    # discount methods
    def get_all_discounts(self):
        self.cursor.execute("""
               select * from discounts
           """)
        return self.cursor.fetchall()

    def create_discount(self, procent, month_payment):
        success = True
        try:
            self.cursor.execute(
                """
                insert into discounts ('procent', 'month_payment')
                values(?, ?)
                """, (procent, month_payment))
            self.connection.commit()
        except Exception as error:
            success = False
            print(error)
        finally:
            return {"success": success}


    def delete_discount(self, discount_id):
        success = True
        try:
            self.cursor.execute(
                """
                delete from discounts
                where id=(?); """, (discount_id,)
            )
            self.connection.commit()
        except Exception as error:
            success = False
            print(error)
        finally:
            return {"success": success}

    # orders methods
    def add_remonline_order_id(self, remonline_id, order_id):

        response = {"success": True}
        try:
            self.cursor.execute("""
                                       update orders
                                       set remonline_order_id = ?
                                       where id = ? 
                                       """, (int(remonline_id), order_id))
            self.connection.commit()
        except Exception as error:
            print(error)
            response = {"success": False}
        finally:
            return response

    def merge_order(self, source_order, target_order)->dict|None:
        """Merge goods from source to target order. After mergind delete source order"""
        source_goods = ast.literal_eval(source_order.get("goods_list"))
        target_goods = ast.literal_eval(target_order.get("goods_list"))
        target_goods.extend(source_goods)  # merge goods
        target_order['goods_list'] = target_goods

        self.cursor.execute("""update order set goods_list=? where id = ? """, (target_goods, target_order['id'],))
        self.connection.commit()
        self.delete_order(source_order['id'])
        return target_order

    def find_order_by_ttn(self, ttn):
        self.cursor.execute("""
                    select * from orders
                    where ttn = ?
                """, (ttn,))
        return self.cursor.fetchone()

    def find_active_order_by_ttn(self, ttn):
        self.cursor.execute("""
                    select * from orders
                    where ttn = ? and is_completed = 0
                """, (ttn,))
        return self.cursor.fetchone()
    
    def find_order_by_id(self, order_id):
        self.cursor.execute("""
                            select * from orders
                            where id = ?
                        """, (order_id,))
        return self.cursor.fetchone()

    def find_order_by_remonline_id(self, remonline_order_id):
        self.cursor.execute("""
                            select * from orders
                            where remonline_order_id = ?
                        """, (remonline_order_id,))
        return self.cursor.fetchone()

    def get_all_orders(self, telegram_id=None, order_id=None):
        filter = ''
        if telegram_id:
            filter = "where telegram_id = {0}".format(telegram_id)

        if order_id:
            filter = "where id = {0}".format(order_id)
        self.cursor.execute("select * from orders {0}".format(filter))
        return [dict(ix) for ix in self.cursor.fetchall()]

    def get_active_orders(self):
        self.cursor.execute(f"""
            select * from orders where is_completed=0
        """)
        return self.cursor.fetchall()

    def get_active_orders_by_telegram_id(self, telegram_id:int):
        self.cursor.execute(f"""
            select * from orders where is_completed=0 and telegram_id = ?
        """, (telegram_id,))
        return self.cursor.fetchall()
    def set_bonus_order_date_to_previous_month(self, order_id):
        self.cursor.execute(
            """
                update orders
                set date = strftime('%Y-%m-%d %H:%M:%S', 'now', 'start of month', '-1 month')
                where id = {0} 
            """.format(order_id)
        )
        self.connection.commit()

    def get_monthly_finished_orders(self, client_id):
        # self.cursor.execute("""
        #         select * from orders where client_id={0} and is_completed=1
        #         and datetime(date) > datetime('now','-1 month')
        #         """.format(client_id))
        self.cursor.execute("""
                        select * from orders where client_id={0} and is_completed=1
                        and strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'start of month', '-1 month')
                        """.format(client_id))

        return self.cursor.fetchall()

    def get_finished_orders_in_current_month(self, client_id):
        self.cursor.execute("""
                                select * from orders where client_id={0} and is_completed=1
                                and strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'start of month')
                                """.format(client_id))

        return self.cursor.fetchall()

    def update_in_branch_order_datetime(self, order_id):
        self.cursor.execute("""
            update orders
            set in_branch_datetime = strftime('%Y-%m-%d %H:%M:%S', 'now')
            where id = {0}
            """.format(order_id)
        )
        self.connection.commit()
    # def get_in_branch_await_day(self, order_id):
    #     self.cursor.execute("""
    #         select * from order
    #         where id ={0}
    #         and branch_remebmer_count
    #     """.format(order_id))

    def deactivate_order(self, order_id):
        success = None
        try:
            self.cursor.execute(
                """
                update orders
                set 'is_completed' = 1
                where id = {0} 
                """.format(order_id, ))
            success = True
            self.connection.commit()
        except Exception as error:
            print(error)
            success = False
        finally:
            return {"success": success}

    def update_ttn(self, order_id, ttn):
        response = {"success": True}
        try:
            self.cursor.execute("""
                               update orders
                               set ttn = ?
                               where id = ? 
                               """, (ttn, order_id))
            self.connection.commit()
        except Exception as error:
            print(error)
            response = {"success": False}
        finally:
            return response

    def update_prepayment_type(self, order_id):
        self.cursor.execute("""
                   update orders
                   set 'prepayment' = 1
                   where id = {0} 
                   """.format(order_id, ))
        self.connection.commit()

    def change_to_not_prepayment(self, order_id):
        self.cursor.execute("""
                           update orders
                           set 'prepayment' = 0
                           where id = {0} 
                           """.format(order_id, ))
        self.connection.commit()

    def delete_order(self, order_id):
        success = None
        try:
            self.cursor.execute(
                """
                delete from orders
                where id = {0} 
                """.format(order_id, ))
            success = True
            self.connection.commit()
        except Exception as error:
            success = False
        finally:
            return {"success": success}

    def no_paid_along_time(self):
        self.cursor.execute("""
                    select * from orders
                    where is_completed = 0 
                    and is_paid=0 
                    and prepayment=1 
                    and datetime(date, '+1 hour') < datetime('now')     
                """)
        return self.cursor.fetchall()

    def post_orders(self,
                    client_id: int,
                    telegram_id: int,
                    goods_list: str,
                    name: str,
                    last_name: str,
                    prepayment: bool,
                    phone: str,
                    nova_post_address: str,
                    is_paid: bool,
                    description: str = None,
                    ttn: str = None
                    ):

        self.cursor.execute(f"""
            insert into orders 
                (
                client_id,
                telegram_id, 
                goods_list, 
                'name', 
                last_name, 
                prepayment, 
                phone, 
                nova_post_address, 
                is_paid, 
                description, 
                ttn,
                'date'
                 )

            values (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""", (
            client_id,
            telegram_id,
            goods_list,
            name,
            last_name,
            prepayment,
            phone,
            nova_post_address,
            is_paid,
            description,
            ttn
        )
                            )
        self.connection.commit()

        return self.cursor.lastrowid

    def update_branch_remember_count(self, order_id):
        self.cursor.execute(
            """
            update orders
            set branch_remember_count=branch_remember_count+1
            where id={0}
            """.format(order_id,)
        )
        self.connection.commit()

    def update_no_paid_remember_count(self, order_id):
        self.cursor.execute(
            """
            update orders
            set remember_count=remember_count+1
            where id={0}
            """.format(order_id,)
        )
        self.connection.commit()

    def pay_order(self, order_id):
        self.cursor.execute(
            """
            update orders
            set 'is_paid' = 1
            where id = {0}
            """.format(order_id, )
        )
        self.connection.commit()
    # order_updates methods
    def post_order_updates(self, update_type, order_id, order:dict|None=None, details:str|None=None):

        self.cursor.execute(
            """INSERT INTO order_updates ("type", order_id, "order", details) VALUES (?, ?, ?, ?)""",
            (update_type, order_id, str(order), details)
        )

        self.connection.commit()
        return self.find_order_by_id(self.cursor.lastrowid)

    def delete_order_updates(self, order_updates_id):
        response = {"success": True, 'data': "Deleted"}
        try:
            self.cursor.execute(f"""
                                 delete from order_updates
                                 where id=(?); """, (order_updates_id,))
            self.connection.commit()
        except Exception as error:
            print(error)
            response = {"success": False, 'data': error}
        finally:
            return response

    def get_order_updates(self):
        self.cursor.execute(
            """select * from order_updates"""
        )
        return self.cursor.fetchall()
