function onSignIn(googleUser) {
    var xmlhttp = new XMLHttpRequest();
    xmlhttp.onreadystatechange = function () {
        if (xmlhttp.readyState === XMLHttpRequest.DONE) {
            if (xmlhttp.status === 200) {
                console.log(xmlhttp.responseText);
                var skey = xmlhttp.responseText.substring(1, xmlhttp.responseText.length-1);
                window.location.href = "/vi/user/auth_googleaccount/login?skey="+skey+"&token="+googleUser.credential;
                //document.getElementById("myDiv").innerHTML = xmlhttp.responseText;
            } else {
                alert('Failed to fetch skey');
            }
        }
    };
    xmlhttp.open("GET", "/vi/skey", true);
    xmlhttp.withCredentials = true;
    xmlhttp.send();
}
