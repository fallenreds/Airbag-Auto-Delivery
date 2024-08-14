import './App.css';
import {useEffect, useState} from "react";
import Header from "./components/Header/Header";
import {Route, Routes, useNavigate} from "react-router-dom";
import ProductList from "./components/ProductList/ProductList";
import Form from "./components/Form/Form";
import ShopingCartList from "./components/ShopingCartList/ShopingCartList";
import {checkAuthenticated, getGoods, getShoppingCart} from "./hooks/api";
import SuccessPage from "./components/SuccessPage/SuccessPage";
import SingUp from "./components/SignUp/SingUp";
import SingIn from "./components/SignIn/SingIn";
import config from "./config.json"
import SuccessAuth from "./components/SuccessAuth/SuccessAuth";
import React from 'react';

export const settings = config.prod_settings
export const base_url = settings.base_url
export const bonus_id = settings.bonus_id
export const prod_price = settings.prod_price

function App() {
    const tg = window.Telegram.WebApp

    const [authenticated, setAuthenticated] = useState(false)
    const [client, setClient] = useState(null)
    const [goodsState, setGoods] = useState([])
    const [shoppingCartState, setShoppingCart] = useState([])
    const [searchState, setSearch] = useState('')
    const [orderSumaState, setOrderSuma]= useState(0)

    let uid = tg.initDataUnsafe?.user?.id
    

    useEffect(()=>{
        getShoppingCart({setShoppingCart}, uid)
    },[])

    useEffect(()=>{
        getGoods({setGoods})
    },[])

    // setInterval(() =>{
    //     checkAuthenticated({setAuthenticated, setClient}, uid)
    // }, 15000);

    useEffect(()=>{
        checkAuthenticated({setAuthenticated, setClient}, uid)
    },[])

    return(
        <div className="App">
            <Header searchState={searchState} setSearch={setSearch}/>
                <Routes>
                    <Route index element={<ProductList
                        shoppingCartState={shoppingCartState}
                        uid={uid}
                        searchState={searchState}
                        setSearch={setSearch}
                        setClient={setClient}
                        setAuthenticated={setAuthenticated}
                        authenticated={authenticated}
                        client={client}
                        />}/>



                    <Route path={'form'} element={<Form
                        uid={uid}
                        shoppingCartState={shoppingCartState}
                        goodsState={goodsState}
                        orderSumaState={orderSumaState}
                        authenticated={authenticated}
                        client={client}
                        />}/>



                    <Route path={'shcart'} element={<ShopingCartList
                        goodsState={goodsState}
                        setGoods={setGoods}
                        uid={uid}
                        orderSumaState={orderSumaState}
                        setOrderSuma={setOrderSuma}
                        shoppingCartState={shoppingCartState}
                        />}/>
                    <Route path={'successpage'} element={<SuccessPage
                        tg={tg}/>}/>


                    <Route path={'singup'} element={<SingUp
                        setClient={setClient}
                        setAuthenticated={setAuthenticated}
                        authenticated={authenticated}
                        client={client}
                        uid={uid}/>}/>

                    <Route path={'singin'} element={<SingIn
                        setClient={setClient}
                        setAuthenticated={setAuthenticated}
                        authenticated={authenticated}
                        client={client}
                        uid={uid}/>}/>
                    <Route path={"SuccessAuth"} element={<SuccessAuth
                        setClient={setClient}
                        setAuthenticated={setAuthenticated}
                        uid={uid}
                    />}/>
                </Routes>
        </div>
    );
}

export default App
