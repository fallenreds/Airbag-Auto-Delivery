const tg = window.Telegram.WebApp;

export function useTelegram() {



    const onClose = () => {
        tg.close()
    }

    const onToggleButton = () => {
        if(tg.MainButton.isVisible) {
            tg.MainButton.hide();
        } else {
            tg.MainButton.show();
        }
    }
    // const get_uid = () =>{
    //     if(tg.initDataUnsafe?.user.id){
    //         return tg.initDataUnsafe.user.id
    //     }
    //     else{
    //         return 516842877
    //     }
    // }

    return {
        onClose,
        onToggleButton,
        tg,
        user: tg.initDataUnsafe?.user,
        // uid: get_uid()
    }
}