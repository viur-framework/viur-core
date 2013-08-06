//INIT
var templatePath= "static/html"
var env = new nunjucks.Environment(new nunjucks.HttpLoader(templatePath));

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

var page_load ={
    containers: [],
    containerdata: {},
    tpls:{},
    registerContainer:function(container,data,tpl){
        if(this.containers.indexOf(container)==-1){
            this.containerdata[container]=data;
            this.tpls[container]=tpl;
            this.containers.push(container);
        }
    },


    getContent: function(container){
        if (fileExists(this.tpls[container])){
            content = env.macrorender(this.tpls[container],this.containerdata[container]);
        }else{
            var temp = new nunjucks.template(this.tpls[container]);
            content = temp.render(this.containerdata[container]);
        }
        return content;
    },

    render_default: function(container,content){
        $('#'+container).fadeOut(200,function(){
           $('#'+container).html(content);
       }).fadeIn(200);
    },

    render:function(){
        for(var i=0;i<this.containers.length;i++){
            content = this.getContent(this.containers[i]);
            if(typeof(this["render_"+this.containers[i]])==='undefined'){

                this.render_default(this.containers[i],content);
            }else{
                this["render_"+this.containers[i]](this.containers[i],content);
            }
        }
    }
}



function fileExists(url) {
    if(url){
        var req = new XMLHttpRequest();
        req.open('GET', templatePath+"/"+url, false);
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
    JINJA/JAVASCRIPT - getEntry
=================================================================
*/

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


//ERTWEITERN!!! PARAMETER DICT WIE IM ORIGINAL params werden &&
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