import React, {useEffect, useState} from 'react';
import 'react-image-gallery/styles/css/image-gallery.css';
import classes from './BlurImage.module.css';


const BlurImage = ({image}) => {
    // Return image with blur background. Used for diff image size.

    if(!image){ // No image
        image ='https://t3.ftcdn.net/jpg/04/34/72/82/360_F_434728286_OWQQvAFoXZLdGHlObozsolNeuSxhpr84.jpg';
    }

    return (
        <div className={classes.container}>
            <img className={classes.blurIMG} alt='Фото' src={image}/>
            <img className={classes.finalIMG} alt='Фото' src={image}/>
        </div>
    );
};

export default BlurImage;
