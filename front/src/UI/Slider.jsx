import React, { Component } from "react";
import Slider from "react-slick";
import Category from "../components/Category/Category";
import category_data from '../category.json'
import classes from './slider.module.css'

export default class SimpleSlider extends Component {

    render() {
        const settings = {
            arrows: false,
            transition: false,
            dots: true,
            infinite: false,
            swipeToSlide: true,
           // pauseOnDotsHover: true,
            slidesToScroll: 1,
            slidesToShow:3,
            swipeable: true
        };

        const changeCategory = this.props.category

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
                                <Slider  {...settings} >
                                    {
                                        child.map(category => <Category changeCategory={changeCategory} category={category} setSearch={this.props.setSearch}/>)

                                    }

                                </Slider>
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
