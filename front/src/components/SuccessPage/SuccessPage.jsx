import React from 'react';
import classes from "./SuccessPage.module.css";
const SuccessPage = (props) => {

    const tg = window.Telegram.WebApp
    return (
        <div className={classes.success}>
            <img src={require('../../succes_logo.png')} alt={'sfdsd'}/>
           <div style={{textAlign:"center"}}>
               Ви успішно створили замовлення.
               Незабаром, вам прийде повідомлення від нашого магазину з вашим замовленням.
               Тепер ви можете повернутись на головну сторінку боту.
           </div>
            <button onClick={tg.close} className={classes.success_btn}>На головну сторінку</button>
        </div>
    );
};

export default SuccessPage;