import React, {useEffect, useState} from 'react';
import ImageGallery from 'react-image-gallery';
import Modal from 'react-modal';
import 'react-image-gallery/styles/css/image-gallery.css';
import classes from './Good.module.css';
import {get_discount, postShoppingCart} from "../../hooks/api";
import {useNavigate} from "react-router-dom";
import BlurImage from "../BlurImage/BlurImage";
import ModalGallery from "../ModalGallery/ModalGallery";
import GalleryItem from "../ModalGallery/GalleryItem";


const Good = (props) => {
    const uid = props.uid;
    const buyButton = <button onClick={addToShoppingCart}>Придбати</button>;
    const toShoppingCartButton = <button onClick={()=>router('/shcart')} style={{background: "rgba(215, 125, 72, 0.3)"}}>До кошику</button>;
    const cantBuyButton = <button style={{background: "rgba(255,0,0,0.13)", borderColor:"rgba(255,0,0, 1)"}}>Немає в наявності</button>;

    const [buttonState, setButton] = useState(buyButton);
    const [cartState, setCart] = useState(props.carts);
    const [goodState, setGood] = useState(props.good);
    const [showGalleryFunc, setShowGalleryFunc] = useState(null);

    const showGallery = () => {
        if (showGalleryFunc) {
            showGalleryFunc();
        }
    };

    useEffect(()=>{
        setGood(props.good);
    },[props.good]);

    useEffect(()=>{
        setCart(props.carts);
    },[props.carts]);

    const router = useNavigate();


    useEffect(()=>{
        if (props.carts.includes(goodState.id)){
            setButton(toShoppingCartButton);
        }
        else if(goodState.residue===0){
            setButton(cantBuyButton);
        }
        else {
            setButton(buyButton);
        }
    },[goodState,props.carts]);

    function addToShoppingCart (){
        setButton(toShoppingCartButton);
        postShoppingCart(uid, goodState.id);
    }






    return (
        <div className={classes.post}>
            <GalleryItem
            images={goodState.image}
            previewClassName={classes.imageContainer}
            index={0}
            />


            <div className={classes.title}>
                {goodState.title}<p/>
            </div>
            <div className={classes.residue}>
                В наявності: {goodState.residue} шт.
            </div>
            <div className={classes.cost}>
                {goodState.price[284727]}₴<p/>
            </div>

            {buttonState}


        </div>
    );
};

export default Good;
