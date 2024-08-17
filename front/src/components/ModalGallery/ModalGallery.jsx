import React from 'react';
import 'react-image-gallery/styles/css/image-gallery.css';
import Modal from 'react-modal';
import ImageGallery from 'react-image-gallery';
import classes from './ModalGallery.module.css';

const ModalGallery = ({ images, isOpen, onClose, startIndex }) => {
    const galleryImages = images.map(img => ({
        original: img,
        thumbnail: img,
    }));

    return (
        <Modal
            isOpen={isOpen}
            onRequestClose={onClose}
            contentLabel="Image Gallery"
            className={classes.modalContent}
            overlayClassName={classes.modalOverlay}
        >
            <ImageGallery
                items={galleryImages}
                startIndex={startIndex}
                showPlayButton={false}
                showThumbnails={true}
                showFullscreenButton={false}
                useBrowserFullscreen={false}
            />
        </Modal>
    );
};

export default ModalGallery;