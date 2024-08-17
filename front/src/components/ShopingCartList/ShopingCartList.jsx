import React, { useEffect, useState } from 'react';
import classes from "./ShopingCartList.module.css";
import ShopingCart from "../ShopingCart/ShopingCart";
import { getGoods, getShoppingCart, getOrderSuma, get_discount, checkAuth } from "../../hooks/api";
import { useNavigate } from "react-router-dom";

const ShopingCartList = (props) => {
    const router = useNavigate();
    const uid = props.uid;
    const [shoppingCartState, setShoppingCart] = useState([]);
    const [orderSumaState, setOrderSuma] = useState(0);
    const setGoods = props.setGoods;
    const goodsState = props.goodsState;
    const [authenticated, setAuthenticated] = useState(false);
    const [client, setClient] = useState(null);
    const [discount, setDiscount] = useState(0);
    const [childErrors, setChildErrors] = useState({});
    const [parentError, setParentError] = useState(false);

    useEffect(() => {
        checkAuth({ uid }).then(response => {
            if (response.status === true) {
                setAuthenticated(true);
                setClient(response.client_data);
            }
        });
    }, [uid]);

    useEffect(() => {
        getGoods({ setGoods });
    }, [setGoods]);

    useEffect(() => {
        getShoppingCart({ setShoppingCart }, uid);
    }, [uid]);

    useEffect(() => {
        getOrderSuma({ setOrderSuma }, uid);
    }, [uid]);

    useEffect(() => {
        if (authenticated && client) {
            get_discount(client.id).then(response => {
                if (response.data.success === true) {
                    setDiscount(response.data.data.procent);
                }
            });
        }
    }, [authenticated, client]);

    useEffect(() => {
        const hasError = Object.values(childErrors).includes(true);
        setParentError(hasError);
    }, [childErrors]);

    const handleChildErrorChange = (index, childError) => {
        setChildErrors(prevErrors => ({
            ...prevErrors,
            [index]: childError
        }));
    };

    const showDiscount = () => {
        if (discount > 0) {
            return (
                <div
                    style={{
                        color: "rgba(19, 189, 50, 1)",
                        textAlign: "center",
                        fontWeight: "bold",
                        fontSize: "3vw",
                        marginTop: '10px'
                    }}
                >
                    Вам доступна знижка у розмірі {discount}%
                </div>
            );
        }
        return null;
    };

    const toPay = () => {
        if (discount) {
            return (
                <div>
                    <div className={classes.topay} style={{ textDecoration: "line-through", color: "red", fontSize: '3vw' }}>
                        Сума до сплати: {orderSumaState} грн
                    </div>
                    <div className={classes.topay}>
                        Сума до сплати: {orderSumaState - (orderSumaState / 100 * discount)}грн
                    </div>
                </div>
            );
        }
        return <div className={classes.topay}>Сума до сплати: {orderSumaState}</div>;
    };

    const removeCart = (id) => {
        setShoppingCart(shoppingCartState.filter(item => item.id !== id));
    };

    const dsf = () => {
        if (parentError) {
            return <div className={classes.topay} style={{ marginTop: "0px", color:"red"}}>
                Нажаль, товару менше ніж обрано к кошику 😢
            </div>;
        } else if (shoppingCartState.length > 0) {
            return (
                <div>
                    {toPay()}
                    <button onClick={() => router('/form')} className={classes.makeOrder}>
                        Зробити замовлення
                    </button>
                </div>
            );
        } else {
            return (
                <div className={classes.shoppingCartList}>
                    <div className={classes.topay} style={{ marginTop: "0px" }}>
                        Ваш кошик порожній🛒
                    </div>
                    <div>
                        <button onClick={() => router('/')} className={classes.makeOrder}>
                            Повернутись до товарів
                        </button>
                    </div>
                </div>
            );
        }
    };

    return (
        <div className={classes.shoppingCartList}>
            {showDiscount()}
            {shoppingCartState.map((info, index) => (
                <ShopingCart
                    key={info.id}
                    index={index}
                    cart={info}
                    goodsState={goodsState}
                    orderSumaState={orderSumaState}
                    setOrderSuma={setOrderSuma}
                    uid={uid}
                    removeCart={removeCart}
                    onErrorChange={handleChildErrorChange}
                />
            ))}
            {dsf()}
        </div>
    );
};

export default ShopingCartList;
