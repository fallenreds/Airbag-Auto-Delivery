import React, {useEffect, useState} from 'react';
import classes from "../ShopingCart/ShopingCart.module.css";
import {deleteShoppingCart, getOrderSuma, updateShoppingCart} from "../../hooks/api";
import BlurImage from "../BlurImage/BlurImage";
import GalleryItem from "../ModalGallery/GalleryItem";

// eslint-disable-next-line
const test_price = 298792
const prod_price = 284727
const ShopingCart = (props) => {
    const [count, setCount] = useState(props.cart.count);
    const good = props.goodsState.find(item => item.id === props.cart.good_id);
    const [price, setPrice] = useState(good.price[prod_price] * count);
    const [error, setError] = useState(false);
    let image = good.image[0]


    useEffect(() => {
        checkErrorState();
    }, [count, good.residue]);
    function isQuantityError(){
        return count>good.residue
    }

    function checkErrorState() {
        const errorState = isQuantityError();
        if (errorState !== error) {
            setError(errorState);
            props.onErrorChange(props.index, errorState);
        }
    }


    const incrementCount = () => {
        if (count + 1 <= good.residue) {
            setCount(count + 1);
            updateShoppingCart(props.cart.id, count + 1);
            props.setOrderSuma(props.orderSumaState + good.price[prod_price]);
        }
    };

    const decrementCount = () => {
        if (count - 1 > 0) {
            setCount(count - 1);
            updateShoppingCart(props.cart.id, count - 1);
            props.setOrderSuma(props.orderSumaState - good.price[prod_price]);
        }
    };

    const deleteCart = () => {
        props.setOrderSuma(props.orderSumaState - good.price[prod_price] * count);
        deleteShoppingCart(props.cart.id);
        props.removeCart(props.cart.id);
        props.onErrorChange(props.index, false);

    };
    checkErrorState()
    return (
        <div className={classes.shoppingCart}>
            <GalleryItem
                images={good.image}
                previewClassName={classes.imageContainer}
                index={0}
            />
            <div className={classes.content}>
                <div className={classes.info}>
                    <div className={classes.maintext}>{good.title}</div>
                    <div className={classes.price}>{good.price[prod_price]}₴</div>
                    <div className={classes.counter}>
                        <button onClick={decrementCount}>-</button>
                        <span>{count}</span>
                        <button onClick={incrementCount}>+</button>
                    </div>
                    <div style={ {color: error ? 'red' : 'black'} }>В наявності: {good.residue} шт</div>
                    <div className={classes.finalprice}>
                        <div className={classes.finaltext}>До сплати:</div>
                        {good.price[prod_price] * count} ₴
                    </div>
                </div>
            </div>
            <button
                style={{color: "red", marginLeft: "auto", marginBottom: "auto", background: "None", border: "None"}}
                onClick={deleteCart}
            >
                Видалити
            </button>
        </div>
    );
};
export default ShopingCart