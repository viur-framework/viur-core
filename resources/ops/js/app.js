/* 
* Skeleton V1.0.2
* Copyright 2011, Dave Gamache
* www.getskeleton.com
* Free to use under the MIT license.
* http://www.opensource.org/licenses/mit-license.php
* 5/20/2011
*/	

function scrollToPlace(place) {
	$('html,body').animate(
		{
			scrollTop: place.offset().top -60
		},
		{
			duration: 1000
		}
	);
}

function askyesno(q,yesdo,nodo) {
	$( "#dialog-yesno" ).html(q);
	$( "#dialog-yesno" ).dialog({
            resizable: false,
            modal: true,
            buttons: {
                "Yes, do it !": function() {
										if (yesdo=="#") {
											$( this ).dialog( "close" );
										} else {
											window.location.href = yesdo;
										}
                },
                "Nope ...": function() {
										if (nodo=="#") {
											$( this ).dialog( "close" );
										} else {
											window.location.href = nodo;
										}
                    
                }
            }
        });
}


$(document).ready(function() {
	/* Scroll To Top
	================================================== */
	
	
	$(document).ready(function() {
   
 		$('a[href=#top]').click(function(){
        	$('html, body').animate({scrollTop:0}, 'slow');
        	return false;
		});

	$("#navcontainer a").live('click tap', function() {
		var destination = $(this).attr("href");
		scrollToPlace($(destination))
		return false;
	})


	});


	/*  Jquery UI 
	================================================== */
	$(document).ready(function(){
		 //$( document ).tooltip();

		 $(function() {
        $( "input[type=submit]" )
            .button()
			});

	});
	

});