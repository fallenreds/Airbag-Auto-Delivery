import React, {useCallback, useEffect, useState} from 'react';
import './Form.module.css';
import {useTelegram} from "../../hooks/useTelegram";
import ShopingCartList from "../ShopingCartList/ShopingCartList";
import {
    checkAuth,
    checkAuthenticated,
    deleteShoppingCart, get_discount,
    getOrderSuma,
    getShoppingCart,
    postOrder
} from "../../hooks/api";
import {useNavigate} from "react-router-dom";
import classes from "./Form.module.css";


const Form = (props) => {

    let uid = props.uid
    const [name, setName] = useState('');
    const [lastname, setLastName] = useState('');
    const [phone, setPhone] = useState('');
    const [address, setAddress] = useState('');
    const [prepayment, setPrepayment] = useState(false);
    const [description, setDescription] = useState('');
    const [formSuccess, setFormSuccess] = useState(false);
    const {tg} = useTelegram();
    const router = useNavigate()
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
        checkAuth({uid}).then(
            response=>{
                if(response.status===false){
                    router('/singup')
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


    const [shoppingCartState, setShoppingCart] = useState([])

    useEffect(()=>{
        getShoppingCart({setShoppingCart}, uid)
    },[])

    const [orderSumaState, setOrderSuma] = useState(0)
    useEffect(()=>{
        getOrderSuma({setOrderSuma},uid)
    },[])


    const onChangeName = (e) => {
        setName(e.target.value)
    }

    const onChangeLastName = (e) => {
        setLastName(e.target.value)
    }
    const onChangePhone = (e) => {
        setPhone(e.target.value)
    }

    const onChangeAddress = (e) => {
        setAddress(e.target.value)
    }
    const onChangeDescription = (e) => {
        setDescription(e.target.value)
    }
    const onChangePrepayment = (e) => {
        if (e.target.value ===1){
            setPrepayment(false)
        }
        else{
            setPrepayment(true)
        }
    }

    function create_order() {
        postOrder(props.uid,
            shoppingCartState,
            name,
            lastname,
            prepayment,
            phone,
            address,
            description
        )
        shoppingCartState.map(item=>deleteShoppingCart(item.id))
        setFormSuccess(true)
        router('/successpage')
    }
    function showSubmit() {
        if(name && lastname && phone && address) {
            return   <button type={"submit"} className={classes.makeOrder}>Оформити замовлення</button>
        }
    }

    // function isSuccess() {
    //     if(formSuccess===true){
    //         return <>
    //             Вы успешно создали заказ. Для того что бы просмотреть стататуз заказа или его оплатить, нажмите на кнопку статус заказов 📦
    //         </>
    //     }
    // }

    return (
        <div className={classes.form}>
            <form onSubmit={create_order}>
                <h3 style={{textAlign:"center"}}>Будь ласка, введіть ваші дані для відправки вашого замовлення ✍️</h3>
                    <input
                        className={classes.input}
                        type="name"
                        placeholder={"Ім'я"}
                        value={name}
                        onChange={onChangeName}
                        required
                    />
                    <input
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
                <input
                    className={classes.input}
                    type="text"
                    placeholder={'Адреса, відділення Нової Пошти'}
                   // placeholder={'Адресс, отделение Новой Почты'}
                    value={address}
                    onChange={onChangeAddress}
                    required
                />
                <input
                    className={classes.input}
                    type="text"
                    placeholder={'Коментар до відправки'}
                   // placeholder={'Комментрарий к отправке'}
                    value={description}
                    onChange={onChangeDescription}
                />
                <select className={classes.select} name="prepayment" onChange={onChangePrepayment}>
                    <option value="1">Накладений платіж</option>
                    <option value="2">Передплата</option>
                </select>
                <div className={classes.topay}>Сума до сплати: {orderSumaState-orderSumaState/100*discount}грн</div>
                {showSubmit()}
            </form>
            <div className={classes.fakeblock}></div>
        </div>
    );
};

export default Form;