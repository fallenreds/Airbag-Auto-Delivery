import React, { useState } from 'react';
import ModalGallery from './ModalGallery';
import BlurImage from "../BlurImage/BlurImage";


const GalleryItem = ({images, index, previewClassName}) => {
    const [isModalOpen, setModalOpen] = useState(false);


    const openModal = () => setModalOpen(true);
    const closeModal = () => setModalOpen(false);
    let preview = images[0] ? images[0] : 'https://t3.ftcdn.net/jpg/04/34/72/82/360_F_434728286_OWQQvAFoXZLdGHlObozsolNeuSxhpr84.jpg';
    if (images.length===0){
        images = [preview]
    }

    return (
        <div>
            <div onClick={openModal} className={previewClassName}>
                <BlurImage image={preview} />
            </div>
            <ModalGallery
                images={images}
                isOpen={isModalOpen}
                onClose={closeModal}
                startIndex={index}
            />
        </div>
    );
};

export default GalleryItem;