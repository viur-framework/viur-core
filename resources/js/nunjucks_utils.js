//ermöglicht das nutzen der macros also normale TPLs indem die erste und die letzte Zeile entfernt werden!
//ACHTUNG das funktioniert natürlich nur wenn nur ein Macro in der DATEI ist!!!! und ohne params
//eventuell durch angabe des namens des Macros lösbar...

env.macrorender=function(name, ctx) {
        var macrotpl = this.getTemplate(name);

        var lines = macrotpl.tmplStr.split("\n");
        lines = lines.filter(function(v){return v!=""});
        lines.splice(0,1);
        lines.splice(lines.length-1,1);
        macrotpl.tmplStr = lines.join("\n");
        return macrotpl.render(ctx);
    };

function fileExists(file) {
    if(file){
        var req = new XMLHttpRequest();
        req.open('GET', templatePath+"/"+file, false);
        req.send();
        return true;
    } else {
        return false;
    }
}


/*
=================================================================
    JQUERY - load_json
=================================================================
*/
(function($)
{
	$.extend(true,
	{
		load_json : function(path)
		{

            $.ajaxSetup({async:false});
            var data;
			nav = $.getJSON(path)
			.done(function( json ) {
               data = json;
			})
			.fail(function( jqxhr, textStatus, error ) {
			  var err = textStatus + ', ' + error;
			  console.log( "Request Failed: " + err);
              data=[];
			});
             $.ajaxSetup({async:true});
            return data;
		}
	});
})(jQuery);


/*
=================================================================
    JINJA/JAVASCRIPT - ViUR Addons Functions
=================================================================
*/


//get Entry #fixme!
function getEntry(skellist,id){
    if(id==0){
        return skellist[0];
    }else{
        var res=false;
        for(var i=0;i<skellist.length;i++){


            if(skellist[i].id == id){
                return skellist[i];
            }else{
                temp=getEntry(skellist[i].children,id);
                if (temp!=false) {
                    res=temp;
                }
            }
        }
        return res;
    }
}
env.globals["getEntry"]=function(skellist,id){return getEntry(skellist,id);};


//getList  #fixme!
function getList(skellist,key,value){
    var res=[];
    for(var i=0;i<skellist.length;i++){
        if(skellist[i][key] == value){
            res.push(skellist[i]);
        }else{
            temp=getEntry(skellist[i].children,key,value);
            if (temp!=false) {
                res=res.concat(temp);
            }
        }
    }
    return res;
}
env.globals["getList"]=function(skellist,key,value){return getList(skellist,key,value);};

/*
=================================================================
    JINJA/JAVASCRIPT - ViUR Addons Functions
=================================================================
*/

//Shortkeyhack  #fixme!
env.addFilter('shortKey', function(str) {
		return(str)
});


//Translatefunction
function translate (str) {
	try {
		return (viur_translationtable[str])
	} catch(e) {
		console.log("cant translate: "+str)
		return(str)
	}
		
}

env.globals["_"]=function(str){return translate(str);};









