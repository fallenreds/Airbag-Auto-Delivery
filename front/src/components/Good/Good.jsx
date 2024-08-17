import React, {useEffect, useState} from 'react';
import ImageGallery from 'react-image-gallery';
import Modal from 'react-modal';
import 'react-image-gallery/styles/css/image-gallery.css';
import classes from './Good.module.css';
import {get_discount, postShoppingCart} from "../../hooks/api";
import {useNavigate} from "react-router-dom";
import BlurImage from "../BlurImage/BlurImage";

Modal.setAppElement('#root'); // Set the root element for accessibility

const Good = (props) => {
    const uid = props.uid;
    const buyButton = <button onClick={addToShoppingCart}>Придбати</button>;
    const toShoppingCartButton = <button onClick={()=>router('/shcart')} style={{background: "rgba(215, 125, 72, 0.3)"}}>До кошику</button>;
    const cantBuyButton = <button style={{background: "rgba(255,0,0,0.13)", borderColor:"rgba(255,0,0, 1)"}}>Немає в наявності</button>;

    const [buttonState, setButton] = useState(buyButton);
    const [cartState, setCart] = useState(props.carts);
    const [goodState, setGood] = useState(props.good);
    const [isGalleryOpen, setGalleryOpen] = useState(false);
    const [galleryIndex, setGalleryIndex] = useState(0);

    useEffect(()=>{
        setGood(props.good);
    },[props.good]);

    useEffect(()=>{
        setCart(props.carts);
    },[props.carts]);

    const router = useNavigate();
    let image = goodState.image[0];
    if(!image){
        image ='https://t3.ftcdn.net/jpg/04/34/72/82/360_F_434728286_OWQQvAFoXZLdGHlObozsolNeuSxhpr84.jpg';
    }

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

    const handleImageClick = () => {
        setGalleryIndex(0); // Set index to 0 to open on the first image
        setGalleryOpen(true);
    };

    const images = goodState.image.map(img => ({
        original: img,
        thumbnail: img,
    }));

    const closeModal = () => {
        setGalleryOpen(false);
    };

    return (
        <div className={classes.post}>
            <Modal
                isOpen={isGalleryOpen}
                onRequestClose={closeModal}
                contentLabel="Image Gallery"
                className={classes.modalContent}
                overlayClassName={classes.modalOverlay}

            >
                <ImageGallery
                    items={images}
                    startIndex={galleryIndex}
                    onClose={closeModal}
                    showPlayButton={false}
                    showThumbnails={true}
                    showFullscreenButton={false}
                    useBrowserFullscreen={false}
                />
            </Modal>

            <div className={classes.imageContainer} onClick={handleImageClick}>
                <BlurImage image={image}></BlurImage>
            </div>

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
