import React, {useEffect, useState} from 'react';
import classes from "./ShopingCartList.module.css";
import ShopingCart from "../ShopingCart/ShopingCart";
import {getGoods, getShoppingCart, getOrderSuma, get_discount, checkAuth} from "../../hooks/api";
import {useNavigate} from "react-router-dom";

const prod_price = 284727
const ShopingCartList = (props) => {
    const router = useNavigate()
    const uid = props.uid
    const [shoppingCartState, setShoppingCart] = useState([])
    const [orderSumaState, setOrderSuma]= useState(0)
    const setGoods = props.setGoods
    const goodsState = props.goodsState
    const [authenticated, setAuthenticated] = useState()
    const [client, setClient] = useState()
    const [discount, setDiscount] = useState(0)

    useEffect(()=>{
        checkAuth({uid}).then(
            response=>{
                if(response.status===true){

                    setAuthenticated(true)
                    setClient(response.client_data)
                }
            }
        )
    },[])


    useEffect(()=>{
       getGoods({setGoods})
    },[])

    useEffect(()=>{
        getShoppingCart({setShoppingCart}, uid)
    },[])

    useEffect(()=>{
        getOrderSuma({setOrderSuma},uid)
    },[])
    // function getGoodById(good_id){
    //     return goodsState.find((item)=>{
    //
    //         if(item.id===good_id){
    //
    //             return item
    //         }
    //
    //     })
    // }
    // function getOrderSum (){
    //     let suma = 0
    //     shoppingCartState.map((item)=>{
    //         suma = suma+getGoodById(item.good_id).price[prod_price]*item.count
    //     })
    //     return suma
    // }

    if(authenticated===true && client){
        get_discount(client.id).then(
            response=>{
                if(response.data.success===true){
                    console.log(response.data)
                    setDiscount(response.data.data.procent)
                    //return <div>Вам доступна знижка у розмірі {response.data.data.procent}%</div>
                }
            }
        )
    }
    console.log(discount)

    function showDiscount(){
        if(discount>0){
            return <div
                style={
                        {color:"rgba(19, 189, 50, 1)",
                        textAlign:"center",
                        fontWeight:"bold",
                        fontSize:"3vw",
                        marginTop:'10px'}}>
                Вам доступна знижка у розмірі {discount}%
            </div>
        }
    }

    function toPay(){
        if(discount){
            return <div>
                <div className={classes.topay} style={{textDecoration:"line-through", color:"red", fontSize:'3vw'}}>Сума до сплати: {orderSumaState} грн</div>
                <div className={classes.topay}>Сума до сплати: {orderSumaState-orderSumaState/100*discount}грн</div>
            </div>
        }
        return <div className={classes.topay}>Сума до сплати: {orderSumaState}</div>

    }


    function removeCart(id){
        setShoppingCart(shoppingCartState.filter(item=>item.id !== id))
    }

    function dsf(){
        if(orderSumaState!==0) {
            return <div>{toPay()}
                <button onClick={() => router('/form')} className={classes.makeOrder}>Зробити замовлення</button></div>
        }
        else {
            return <div className={classes.shoppingCartList}>
                <div className={classes.topay} style={{marginTop:"0px"}}>Ваш кошик порожній🛒</div>
                <div><button onClick={() => router('/')} className={classes.makeOrder}>Повернутись до товарів</button></div>
            </div>
        }
    }

    return (

        <div className={classes.shoppingCartList}>

            {showDiscount()}
            {shoppingCartState.map(info=>

                <ShopingCart cart={info} goodsState={goodsState} orderSumaState={orderSumaState} setOrderSuma={setOrderSuma} uid={uid} removeCart={removeCart}/>
            )}
            {dsf()}

        </div>
    );
};

export default ShopingCartList;