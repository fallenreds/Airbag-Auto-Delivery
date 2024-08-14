import React, { Component } from 'react';
import ReactDOM from 'react-dom';
import "react-responsive-carousel/lib/styles/carousel.min.css"; // requires a loader

import category_data from "../category.json";
import classes from "./slider.module.css";
import Slider from "react-slick";
import Category from "../components/Category/Category";
import Carousel from "react-multi-carousel";
import "react-multi-carousel/lib/styles.css";
const responsive = {
    superLargeDesktop: {
        // the naming can be any, depends on you.
        breakpoint: { max: 4000, min: 3000 },
        items: 5
    },
    desktop: {
        breakpoint: { max: 3000, min: 1024 },
        items: 5
    },
    tablet: {
        breakpoint: { max: 1024, min: 464 },
        items: 3
    },
    mobile: {
        breakpoint: { max: 464, min: 0 },
        items: 3
    }
};
export default class DemoCarousel extends Component {

    render() {
        const changeCategory = this.props.category
        const settings = {
            showDots:true,
            arrows:false,
            minimumTouchDrag:1,
            swipeable: true
        };
        function get_сhildrens (parent_id) {
            return category_data.data.filter((ct)=>ct.parent_id === parent_id)
        }

        return (
            <div className={classes.upslider}>
                {category_data.data.map(category => {
                    if(category.parent_id === undefined) {
                        const child = get_сhildrens(category.id)
                        return (

                            <div className={classes.nodots}>
                                <div className={classes.category_text}>{category.title}</div>
                                <Carousel  {...settings} responsive={responsive}>
                                    {
                                        child.map(category => <Category changeCategory={changeCategory} category={category} setSearch={this.props.setSearch}/>)

                                    }

                                </Carousel>
                            </div>


                        )
                    }
                    else{
                        return null
                    }
                })}
            </div>
        );
    }
}

