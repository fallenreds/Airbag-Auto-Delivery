import React from 'react';
import classes from "./Category.module.css";
const Category = (...props) => {

    let image = props[0].category.image
    const rq = require('../../images/category-logo/'+image)

    const changeCategory= props[0].changeCategory
    const categoryId = props[0].category.id

    const selectCategory = ()=>{
        props[0].setSearch('')
        changeCategory(categoryId)

    }
    return (
        <a href={"#section1"} style={{textDecoration:"none", color: "var(--tg-theme-text-color)", fontWeight:"bold"}}><div  onClick={selectCategory} className={classes.category}>
            <img src={rq} alt ='img' />
            {props[0].category.title}
        </div></a>
    );
};

export default Category;
