import React, {useEffect, useState} from 'react';
import classes from "../ShopingCart/ShopingCart.module.css";
import {deleteShoppingCart, getOrderSuma, updateShoppingCart} from "../../hooks/api";

// eslint-disable-next-line
const test_price = 298792
const prod_price = 284727
const ShopingCart = (props) => {

    const [count, setCount] = useState(props.cart.count);
    const good = props.goodsState.filter(item=>item.id===props.cart.good_id)[0]
    const [price, setPrice] = useState(good.price[prod_price]*count);
    let cart_id = props.cart.id

    useEffect(()=>{
        setPrice()
    })
    function updateSuma(){
        getOrderSuma(props,props.uid)
    }
    function deleteCart(){
        props.setOrderSuma(props.orderSumaState-good.price[prod_price]*count)
        deleteShoppingCart(cart_id)
        props.removeCart(cart_id)
    }

    function incrementCount() {
        if(count+1 <= good.residue){
            setCount(count+1)
            updateShoppingCart(cart_id, count+1)

            props.setOrderSuma(props.orderSumaState+good.price[prod_price])
        }
    }
    function decrementCount() {
        if(count-1>0){
            setCount(count-1)
            updateShoppingCart(cart_id, count-1)
            props.setOrderSuma (props.orderSumaState-good.price[prod_price])
        }

    }



    let image = good.image[0]
    if(!image){
        image ='https://t3.ftcdn.net/jpg/04/34/72/82/360_F_434728286_OWQQvAFoXZLdGHlObozsolNeuSxhpr84.jpg'
    }
    return (
        <div className={classes.shoppingCart}>
            <div className={classes.imageContainer}>

                <img className={classes.blurIMG} alt='Фото' src={image}/>
                <img className={classes.finalIMG} alt='Фото' src={image}/>

            </div>
            <div className={classes.content}>


            <div className={classes.info}>
                <div className={classes.maintext}>{good.title}</div>
                <div className={classes.price}>{good.price[284727]}₴</div>
                <div className={classes.counter}>
                    <button onClick={decrementCount}>-</button>
                    <span>{count}</span>
                    <button onClick={incrementCount}>+</button>
                </div>
                <div >В наявності: {good.residue} шт</div>

                <div className={classes.finalprice}>

                    <div className={classes.finaltext}>
                        До сплати:
                    </div>

                    {good.price[prod_price]*count} ₴
                </div>
            </div>
            </div>

            <button
                style={{color: "red", marginLeft: "auto", marginBottom:"auto", background:"None", border: "None"}}
                onClick={deleteCart}
            >
                Видалити
            </button>
        </div>
    );
};

export default ShopingCart;