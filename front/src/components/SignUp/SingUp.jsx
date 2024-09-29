import React, {useEffect, useState} from 'react';
import {useNavigate} from "react-router-dom";
import classes from "./SignUp.module.css";
import {checkAuth, checkAuthenticated, checkFreeLogin, checkFreePhone, postClient} from "../../hooks/api";

const SingUp = (props) => {
    const router = useNavigate()
    const uid = props.uid

    const [name, setName] = useState('');
    const [lastname, setLastName] = useState('');
    const [phone, setPhone] = useState('');
    const [login, setLogin] = useState('');
    const [password, setPassword] = useState('');
    const [passwordAccept, setPasswordAccept] = useState('');

    const [phoneError, setPhoneError] = useState('');
    const [loginError, setLoginError] = useState('');
    const [passwordError, setPasswordError] = useState('');
    const [passwordAcceptError, setPasswordAcceptError] = useState('');

    const  [isValidForm, setIsValidForm] = useState(false);
    const  [isFreeLogin, setIsFreeLogin] = useState(true);
    const  [isFreePhone, setIsFreePhone] = useState(true);


    useEffect(()=>{
        checkAuth({uid}).then(
            response=>{
                if(response.status===true){
                    router(-1)
                }
            }
        )
    },[])

    useEffect(()=>{
        if(phoneError || loginError || passwordError || passwordAcceptError || name==='' || login==='' || lastname===''||phone===''||password===''||passwordAccept===''){
            setIsValidForm(false)
        }
        else{
            setIsValidForm(true)
        }
    })
    useEffect(()=>{
        checkFreeLogin({setIsFreeLogin},login)
    },[login])

    useEffect(()=>{
        checkFreePhone({setIsFreePhone}, phone)
    },[phone])


    function goToSingIn(){
        router("/singin")
    }
    
    const onChangeName = (e) => {
        setName(e.target.value)
    }

    const onChangeLastName = (e) => {
        setLastName(e.target.value)
    }
    const onChangePhone = (e) => {
        setPhone(e.target.value)

        let re = new RegExp("^\\+38(0\\d{9})");
        if(e.target.length>9){
            checkFreePhone({setIsFreePhone}, phone)
        }
        if(e.target.value ===''){
            setPhoneError("")
        }
        else if(!re.test(e.target.value)){
            setPhoneError("Введіть номер телефону у форматі +380XXXXXXXXX")
        }
        else {
            setPhoneError("")
        }
    }

    const onChangeLogin = (e) => {
        checkFreeLogin({setIsFreeLogin},e.target.value)
        let re = new RegExp("^[A-Za-z\\d@$!%_*#?&]{6,}");
        // let re = new RegExp("^(?=.*[A-Za-z])(?=.*\\d)(?=.*[@$!%*_#?&])[A-Za-z\\d@$!%_*#?&]{6,}");
        setLogin(e.target.value)

        if(e.target.value ===''){
            setLoginError("")
        }
        else if(e.target.value.length <6 || e.target.value.length >18){
            setLoginError("Довжина логіна повинна бути від 6 до 18 символів.")
        }
        // else if(!re.test(e.target.value)){
        //     setLoginError("Мінімум шість символів, мінімум одна літера, одна цифра та один спеціальний символ:")
        // }
        else {
            setLoginError("")
        }
    }

    const onChangePasswordAccept = (e) => {
        setPasswordAccept(e.target.value)

        if(e.target.value ===''){
            setPasswordAcceptError("")
        }
        else if(e.target.value!==password){
            setPasswordAcceptError("Паролі не співпадають")
        }
        else {
            setPasswordAcceptError("")
        }
    }

    const onChangePassword = (e) => {
        // let re = new RegExp("^(?=.*[A-Za-z])(?=.*\\d)(?=.*[@$!%_*#?&])[A-Za-z\\d@$!%_*#?&]{6,}");
        let re = new RegExp("^[A-Za-z\\d@$!%_*#?&]{6,}");
        setPassword(e.target.value)

        if(e.target.value ===''){
            setPasswordError("")
        }
        else if(e.target.value.length <6 || e.target.value.length >20){
            setPasswordError("Довжина пароля повинна бути від 6-ти до 20-ти символівв")
        }
        else {
            setPasswordError("")
        }
    }
    
    function finalAction() {
       // router('/shcart')
        router('/SuccessAuth')

    }



    function submitForm(event) {
        event.preventDefault()
        checkFreeLogin({setIsFreeLogin}, login)
        checkFreePhone({setIsFreePhone}, phone)

        if(isFreeLogin && isFreePhone){
            postClient(uid, name, lastname, login, password, phone)
            finalAction()
        }
        if(isFreeLogin===false){
            setLoginError("Клієнт з таким логіном вже творений, оберіть інший логін, або увійдіть в аккаунт")
        }
        if(isFreePhone===false){
            setPhoneError("Телефон повинен бути унікальний для кожного клієнта. Якщо ви вже реєструвались за цим номером, будь ласка, увійдіть у аккаунт.")
        }
    }


    return (

        <div className={classes.form}>
            <div style={{ textAlign: 'center'}}>
                Ще не зареєстровані? Зареєстровані клієнти одержують знижки від покупок!
            </div >
            <form onSubmit={submitForm}>
                <input
                    minLength={2}
                    className={classes.input}
                    type="name"
                    placeholder={"Ім'я"}
                    value={name}
                    onChange={onChangeName}
                    required
                />
                <input
                    minLength={3}
                    className={classes.input}
                    type="text"
                    placeholder={'Прізвище'}
                    value={lastname}
                    onChange={onChangeLastName}
                    required
                />
                <input
                    className={classes.input}
                    id="phone"
                    name="phone"
                    pattern="^\+?3?8?(0\d{9})$"
                    type="tel"
                    placeholder={'Номер телефону +380'}
                    value={phone}

                    onChange={onChangePhone}
                    required
                />
                <div style={{color:"red",  marginBottom:"0px", fontSize: 12}}>{phoneError}</div>
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
                <input
                    className={classes.input}
                    id="passwordAccept"
                    name="passwordAccept"
                    type="password"
                    placeholder={'Повторіть пароль'}
                    value={passwordAccept}
                    minLength={6}
                    onChange={onChangePasswordAccept}
                    required
                />
                <div style={{color:"red",  marginBottom:"0px", fontSize: 12}}>{passwordAcceptError}</div>

                <div style={{marginTop:"5px", fontSize: 12}}>
                    Введіть дані для авторизації та натисніть "Зареєструватись".
                </div>
                <div className={classes.buttonList}>
                    <button className={classes.singButton} disabled={!isValidForm} type={"submit"}>
                        Зареєструватись
                    </button>
                </div>

            </form>
            <div className={classes.fakeblock}></div>
        </div>
    );
};

export default SingUp;