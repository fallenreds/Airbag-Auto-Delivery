import React from 'react';
import classes from "./Header.module.css"
import {useLocation, useNavigate} from 'react-router-dom';
import AuthButton from "../Button/AuthButton/AuthButton";

const Header = (props) => {
    const router = useNavigate()
    let location= useLocation()
    // function goShoppingCart() {
    //     window.Telegram.WebApp.openLink('')
    // }
    // function goProductlist() {
    //     window.Telegram.WebApp.openLink('/')
    // }

    function showBackButton(){
        if(location.pathname !=='/'){
            return <div className={classes.shopping_cart}>
                <button onClick={()=>router('/')}><img src={require("../../back_icon.png")} alt ='img'/></button>
            </div>
        }
    }
    function showShoppingCartButton(){
        if(location.pathname !=='/shcart'){
            return <div className={classes.shopping_cart}>
                <button onClick={()=>router('/shcart')}><img src={require("../../shcard_icon2.png")} alt ='img'/></button>
            </div>
        }
    }

    const onSearch = (e) => {
        props.setSearch(e.target.value)


    }

    function searchSubmit(event) {
        event.preventDefault()
        document.querySelector("#section2").scrollIntoView()
    }

    function showSearchBar(){
        if(location.pathname ==='/'){
            return <form className={classes.seacrchcontainer} onSubmit={searchSubmit}>
                <input
                    className={classes.input}
                    type="text"
                    placeholder={'Пошук'}
                    defaultValue=''
                    onChange={onSearch}
                    value={props.searchState}

                    // onClick={() =>
                    //     //window.location.href = "#section1"
                    //     //document.querySelector("#section1").scrollIntoView()
                    // }
                    // onFocus={()=>
                    //     document.querySelector("#section2").scrollIntoView()
                    // }

                />
            </form>

        }
        else{
            return <div className={classes.hideinput}></div>
        }
    }
    function showSearchIcon(){
        if(location.pathname ==='/'){
            return <div className={classes.shopping_cart}>
            <button className={classes.shopping_cart} onClick= {()=>document.querySelector("#section2").scrollIntoView()}>
                <img src={require("../../search.png")} alt ='img'/></button>
            </div>
        }


    }

    return (
        <div className={classes.header}>

            {showSearchBar()}
            {showSearchIcon()}
            <AuthButton clickFunction={()=>router('/singup')} label={"Зареєструватись"}/>
            <AuthButton clickFunction={()=>router('/singin')} label={"Увійти в аккаунт"}/>
            {showShoppingCartButton()}
            {showBackButton()}


        </div>


    );
};

export default Header;