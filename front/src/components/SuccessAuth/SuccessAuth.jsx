import React, {useEffect} from 'react';
import classes from "./SuccessAuth.module.css";
import AuthButton from "../Button/AuthButton/AuthButton";
import {useNavigate} from "react-router-dom";
import {checkAuth} from "../../hooks/api";

const SuccessAuth = (props) => {
    const uid = props.uid
    let router = useNavigate()

    useEffect(()=>{
        checkAuth({uid}).then(
            response=>{
                if(response.status===true){

                    props.setAuthenticated(true)
                    props.setClient(response.client_data)
                }
            }
        )
    },[])


    return (
        <div className={classes.success}>
            <img src={require('../../succes_logo.png')} alt={'sfdsd'}/>
            <div style={{textAlign:"justify"}}>
                Ви успішно увійшли до аккаунту🎉 Дякуємо за авторизацію. Ви можете перейти до перегляду товарів, або одразу до кошику.
            </div>

            <div className={classes.AuthButton}>
                <AuthButton clickFunction={()=>router('/')} label={"Товари📦"}/>
            </div>
            <div className={classes.AuthButton}>
                <AuthButton clickFunction={()=>router('/shcart')} label={"До кошику🛒"}/>
            </div>

        </div>
    );
};

export default SuccessAuth;