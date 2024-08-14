import React, {useEffect, useState} from 'react';
import {useNavigate} from "react-router-dom";
import classes from "./SignIn.module.css";
import {checkAuth, checkFreeLogin, logIn, postClient} from "../../hooks/api";

const SingIn = (props) => {
    const router = useNavigate()
    const uid = props.uid

    const [login, setLogin] = useState('');
    const [password, setPassword] = useState('');


    const [loginError, setLoginError] = useState('');
    const [passwordError, setPasswordError] = useState('');


    const [isValidForm, setIsValidForm] = useState(false);
    const [isFreeLogin, setIsFreeLogin] = useState();
    useEffect(()=>{
        checkAuth({uid}).then(
            response=>{
                if(response.status===true){
                    router('/SuccessAuth')
                }
            }
        )
    },[])
    function goToSingUp(){
        router("/singup")
    }

    useEffect(()=>{
        if(loginError || passwordError || login==='' ||password===''){
            setIsValidForm(false)
        }
        else{
            setIsValidForm(true)
        }
    })

    const onChangeLogin = (e) => {
        let re = new RegExp("^[A-Za-z\\d@$!%_*#?&]{6,}");
        //let re = new RegExp("^(?=.*[A-Za-z])(?=.*\\d)(?=.*[@$!%*_#?&])[A-Za-z\\d@$!%_*#?&]{6,}");
        setLogin(e.target.value)

        if(e.target.value ===''){
            setLoginError("")
        }
        else if(e.target.value.length <6 || e.target.value.length >18){
            setLoginError("Довжина логіна повинна бути від 6-ти до 18-ти символів.")
        }
        // else if(!re.test(e.target.value)){
        //     setLoginError("Мінімум шість символів, мінімум одна літера, одна цифра та один спеціальний символ:")
        // }
        else {
            setLoginError("")

        }
    }


    const onChangePassword = (e) => {
        let re = new RegExp("^[A-Za-z\\d@$!%_*#?&]{6,}");
       // let re = new RegExp("^(?=.*[A-Za-z])(?=.*\\d)(?=.*[@$!%_*#?&])[A-Za-z\\d@$!%_*#?&]{6,}");
        setPassword(e.target.value)

        if(e.target.value ===''){
            setPasswordError("")
        }
        else if(e.target.value.length <6 || e.target.value.length >20){
            setPasswordError("Довжина пароля повинна бути від 6-ти до 20-ти символів.")
        }
        else {
            setPasswordError("")
        }
    }


    function submitForm(event) {
        event.preventDefault()
        checkFreeLogin({setIsFreeLogin},login)

        if(!isFreeLogin){
            logIn(login,password,uid).then(response=>{
                if(response.data.success===true){
                    router("/shcart")
                }
                if(response.data.detail==="client not found"){
                    setLoginError("Клієнта не знайдено")
                }
                if(response.data.detail==="Incorrect password"){
                    setPasswordError("Неправильний пароль")
                }
            })
        }
        else {
            setLoginError("Немає такого користувача")
        }
    }

    return (

        <div className={classes.form}>
            <div style={{ textAlign: 'center'}}>
                Введіть ваш логін та пароль
            </div >
            <form onSubmit={submitForm}>
                <input
                    className={classes.input}
                    id="login"
                    name="login"
                    pattern="^[A-Za-z0-9]+([A-Za-z0-9]*|[._-]?[A-Za-z0-9]+)*$"
                    type="text"
                    placeholder={'Логін'}
                    value={login}
                    minLength={6}
                    onChange={onChangeLogin}
                    required
                />
                <div style={{color:"red",  marginBottom:"0px", fontSize: 12}}>{loginError}</div>
                <input
                    className={classes.input}
                    id="password"
                    name="password"
                    type="password"
                    placeholder={'Пароль'}
                    value={password}
                    minLength={6}
                    onChange={onChangePassword}
                    required
                />
                <div style={{color:"red",  marginBottom:"0px", fontSize: 12}}>{passwordError}</div>
                <div style={{marginTop:"5px", fontSize: 12}}>
                    Ще не зареєстровані? Натисніть кнопку "Зареєструватися" для реєстрації облікового запису.
                </div>
                <div className={classes.buttonList}>
                    <button className={classes.singButton} onClick={goToSingUp}  type={"submit"}>
                        Зареєструватись
                    </button>
                    <button  className={classes.singButton} disabled={!isValidForm} type={"submit"}>
                        Увійти
                    </button>
                </div>

            </form>
            <div className={classes.fakeblock}></div>
        </div>
    );
};

export default SingIn;