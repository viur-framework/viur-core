var vi_mc_validmessagetypes = ["info"];
var vi_mc_messages=[{message:"test ......",type:"info",read:false}];

function vi_mc($scope) {
	$scope.vi_mc_messages = vi_mc_messages;
	
	$scope.vi_mcaddMessage = function(message,type,autohide) {
	    $scope.vi_mc_messages.push({message:message,type:type,read:false});
	  };
}

function vi_mc_initialize () {
	
} 

function log(message,type,autohide) {
	console.log("message: "+message);
	if (typeof ($scope) == 'undefined') {
		console.log("storing message cause mc is not initialized..");
		vi_mc_messages.push({message:message,type:type,read:false});		
	} else {
		$scope.vi_mcaddMessage(message,type,autohide);
	}
}
