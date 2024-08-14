import axios from "axios";

import {base_url} from "../App";
import {bonus_id} from "../App";


function sortResude(item) {

    if (item.residue>0) {
        return -1;
    }
    if(item.residue===0){
        return 1
    }
}

export function getGoods(props) {
    axios.get(base_url+'api/v1/goods').then(

        response=>{
            props.setGoods(response.data.data.sort((item)=>sortResude(item)).filter(item=> item.id!==bonus_id))
        }
    )
}



export function getShoppingCart(props, telegramId) {
    axios.get(
        base_url+'api/v1/shoppingcart/'+telegramId)

        .then(
        response=>{
            props.setShoppingCart(response.data)
        }
    )
}


export function postShoppingCart(telegramId, goodId) {
    axios.post(
        base_url + 'api/v1/shoppingcart/',
        {
            "telegram_id": telegramId,
            "good_id": goodId,

        })

        .then(response=>{
        return response.status
    })
}

export function deleteShoppingCart(CartId) {
    axios.delete(
        base_url + 'api/v1/shoppingcart/'+CartId)

        .then(response=>{
        console.log(response.status)
    })
}

export function updateShoppingCart(CartId, count) {
    axios.patch(
        base_url + 'api/v1/shoppingcart/'+CartId,
        {"count":count})

        .then(response=>{
            console.log(response.status)
        })
}

export function postOrder(telegramId,
                          goodsList,
                          name,
                          lastName,
                          prepayment,
                          phone,
                          address,
                          description,
                          ) {
    axios.post(
        base_url + 'api/v1/order/',
        {
            "telegram_id": telegramId,
            "goods_list": goodsList,
            "name": name,
            "last_name": lastName,
            "prepayment":  prepayment,
            "phone": phone,
            "nova_post_address": address,
            "description":description
        }
    )

        .then(response=>{
            return response.status
        })
}

export function getOrderSuma(props, uid) {
    axios.get(base_url+"api/v1/ordersuma/"+uid).then(
        response=>{
            props.setOrderSuma(response.data)
        }
    )
}

export function checkFreeLogin(props,login) {
    axios.get(base_url+"api/v1/checkfreelogin/"+login).then(
        response=>{
           props.setIsFreeLogin(response.data)
        }
    )
}

export function checkFreePhone(props, phone) {
    axios.get(base_url+"api/v1/checkfreephone/"+phone).then(
        response=>{
            props.setIsFreePhone(response.data)
        }
    )

}

export function postClient(uid,
                          name,
                          lastName,
                          login,
                          password,
                          phone,

) {
    axios.post(
        base_url + 'api/v1/singup/',
        {
            "telegram_id": uid,
            "name": name,
            "last_name": lastName,
            "login": login,
            "password": password,
            "phone": phone
        }
    )

        .then(response=>{
            return response.status
        })
}

export function checkAuthenticated(props, uid) {
    axios.get(base_url+"api/v1/isauthendicated/"+uid).then(
        response=>{
            if(response.data.success){
                props.setAuthenticated(true)
                props.setClient(response.data)
            }
            else {
                props.setAuthenticated(false)
                props.setClient({})
            }

        }
    )
}

export function checkAuth(props) {
    return axios.get(base_url+"api/v1/isauthendicated/"+props.uid).then(
        response=>{
            if(response.data.success){
                return {
                    status: true,
                    client_data: response.data
                }

            }
            else {
                return {
                    status: false,
                    client_data: {}
                }
            }
        }
    )
}

export function logIn(login, password, telegramId) {
    return axios.post(
        base_url + 'api/v1/signin/',
        {
            "login": login,
            "password": password,
            "telegram_id": telegramId
        }
    )
}

export function get_discount(client_id) {
    return axios.get(base_url+"api/v1/monthdiscount/"+client_id)
}