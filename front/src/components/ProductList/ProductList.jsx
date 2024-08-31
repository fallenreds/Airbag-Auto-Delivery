import './ProductList.module.css';
import category from "../../category.json";
import Good from "../Good/Good";
import SimpleSlider from "../../UI/Slider";
import React, {useEffect, useState} from "react";
import {checkAuth, checkAuthenticated, get_discount, getGoods, getShoppingCart} from "../../hooks/api";
import classes from "./ProductList.module.css";
import AuthButton from "../Button/AuthButton/AuthButton";
import {useNavigate} from "react-router-dom";
import { Link, animateScroll as scroll } from "react-scroll";
import DemoCarousel from "../../UI/newSlider";




const ProductList = (props) => {

    const uid = props.uid

    const [categoryState, setCategory] = useState(null)
    const [shoppingCartState, setShoppingCart] = useState(props.shoppingCartState)
    const [goodsState, setGoods] = useState([])
    const [authenticated, setAuthenticated] = useState()
    const [client, setClient] = useState()
    const [discount, setDiscount] = useState(0)

    let router = useNavigate()

    useEffect(()=>{
        getShoppingCart({setShoppingCart}, uid)
    },[categoryState, props.searchState, uid])

    useEffect(()=>{
        getGoods({setGoods})
    },[])


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
    if(authenticated===true && client){
        get_discount(client.id).then(
            response=>{
                if(response.data.success===true){
                    setDiscount(response.data.data.procent)
                    //return <div>Вам доступна знижка у розмірі {response.data.data.procent}%</div>
                }
            }
        )
    }

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



    function showClientInfo(){
        if(authenticated===true){
            return <div style={{marginTop:"45px", fontSize:"18px", fontFamily:"Montserrat", textAlign:"center"}}>
                Ласкаво просимо, {client.name} {client.last_name}
                {showDiscount()}
            </div>
        }
        else {
            return <>
                {/*<div className={classes.AuthContainer}>Шановний клієнт, ви маєте змогу зарєструватись, або увійти в аккаунт.</div>*/}
                {/*<div className={classes.AuthButtonContainer}>*/}
                {/*    <AuthButton clickFunction={()=>router('/singup')} label={"Зареєструватись"}/>*/}
                {/*    <AuthButton clickFunction={()=>router('/singin')} label={"Увійти в аккаунт"}/>*/}
                {/*</div>*/}

            </>
        }
    }



    function textFiltering (searchText) {
        // eslint-disable-next-line
        return goodsState.filter(
            // eslint-disable-next-line
            (item)=>{
                if(item.title.toLowerCase().includes(searchText.toLowerCase())) {
                    return true
                }
            }
        )
    }

    // eslint-disable-next-line
    const cartsGoods = shoppingCartState.filter(item=> item.telegram_id === uid).map(item=>item.good_id)

    function categoryFilter(categoryId) {
        setCategory(categoryId)
    }
    function restartCategory() {
        categoryFilter(null)
    }

    let categoryLabel = categoryState === null ? "Усі товари":
                        category.data.find(item=>item.id === categoryState).title



    function filterGoodByCategory() {
        if(props.searchState){

            return textFiltering(props.searchState)
        }
        if(categoryState === null){
            return goodsState
        }
        // eslint-disable-next-line
        return goodsState.filter(item=>item.category.id===categoryState)


    }

    function showClearFiler(){

        if (categoryLabel !== "Усі товари"){
            return <button  onClick={restartCategory} style={{background:"none", border: "none"}}>Очистити фільтр категорій ❌</button>
        }

    }

    //const tg = window.Telegram.WebApp
    return (

        <div className={classes.form}>

            {showClientInfo()}

            {/*<SimpleSlider category={categoryFilter} setSearch={props.setSearch} />*/}
            <DemoCarousel category={categoryFilter} setSearch={props.setSearch} />
            <div className={classes.maintext}>
                <section id={"section2"}><section id="section1"><h3>{categoryLabel}</h3>  </section></section>
                {showClearFiler()}

            </div>



            <div className={classes.postlist}>
                {filterGoodByCategory().map(good=> <Good
                        good={good} carts={cartsGoods} uid={uid}
                        />
                    )}
            </div>
            <div className={classes.fakeblock}></div>
            version 1.2
        </div>


    );
};

export default ProductList;

