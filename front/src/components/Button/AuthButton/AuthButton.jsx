import React from 'react';
import classes from "./AuthButton.module.css";
const AuthButton = (props) => {
    return (
        <div className={classes.AuthButton}>
            <button onClick={props.clickFunction}>{props.label}</button>
        </div>
    );
};

export default AuthButton;