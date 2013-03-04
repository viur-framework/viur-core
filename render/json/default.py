# -*- coding: utf-8 -*-
import json
from server import bones
from collections import OrderedDict
import logging
class DefaultRender( object ):
	
	def __init__(self, parent=None, *args, **kwargs ):
		super( DefaultRender,  self ).__init__( *args, **kwargs )
	
	def renderSkelStructure(self, skel ):
		"""Dumps the Structure of a Skeleton"""
		if isinstance( skel, dict ):
			return( None )
		res = OrderedDict()
		for key, bone in skel.items() :
			if "__" not in key:
				_bone = getattr( skel, key )
				if( isinstance( _bone, bones.baseBone ) ):
					res[ key ] = {	"descr": _(_bone.descr), 
								"type": _bone.type, 
								"visible":_bone.visible,
								"required": _bone.required,
								"readonly": _bone.readOnly, 
								"params": _bone.params
								}
					if key in skel.errors.keys():
						res[ key ][ "error" ] = skel.errors[ key ]
					else:
						res[ key ][ "error" ] = None
					if isinstance( _bone, bones.relationalBone ):
						if isinstance( _bone, bones.hierarchyBone ):
							boneType = "hierarchy"
						elif isinstance( _bone, bones.treeItemBone ):
							boneType = "treeitem"
						else:
							boneType = "relational"
						res[key]["type"]="%s.%s" % (boneType,_bone.type)
						res[key]["multiple"]=_bone.multiple
						res[key]["format"] = _bone.format
					if( isinstance( _bone, bones.treeDirBone ) ):
							boneType = "treedir"
							res[key]["type"]="%s.%s" % (boneType,_bone.type)
							res[key]["multiple"]=_bone.multiple
					if ( isinstance( _bone, bones.selectOneBone ) or  isinstance( _bone, bones.selectMultiBone ) ):
						res[key]["values"] = dict( [(k,_(v)) for (k,v) in _bone.values.items() ] )
					if ( isinstance( _bone, bones.dateBone ) ):
						res[key]["time"] = _bone.time
						res[key]["date"] = _bone.date
					if( isinstance( _bone, bones.textBone ) ):
						res[key]["validHtml"] = _bone.validHtml
					if( isinstance( _bone, bones.stringBone ) ):
						res[key]["multiple"] = _bone.multiple
					if( isinstance( _bone, bones.numericBone )):
						res[key]["precision"] = _bone.precision
						res[key]["min"] = _bone.min
						res[key]["max"] = _bone.max
					if( isinstance( _bone, bones.documentBone ) ):
						res[key]["extensions"] = [ self.renderTextExtension( x ) for x in _bone.extensions ]
		return( [ (key, val) for key, val in res.items()] )
	
	def renderTextExtension(self, ext ):
		e = ext()
		return( {"name": e.name, 
				"descr": _( e.descr ), 
				"skel": self.renderSkelStructure( e.dataSkel() ) } )
	
	def renderSkelValues( self, skel ):
		"""Prepares Values of one Skeleton for Output"""
		if isinstance( skel, dict ):
			return( skel )
		res = {}
		for key in dir( skel ):
			if "__" not in key:
				_bone = getattr( skel, key )
				if isinstance( _bone, bones.dateBone ):
					if _bone.value:
						if _bone.date and _bone.time:
							res[key] = _bone.value.strftime("%d.%m.%Y %H:%M:%S")
						elif _bone.date:
							res[key] = _bone.value.strftime("%d.%m.%Y")
						else:
							res[key] = _bone.value.strftime("%H:%M:%S")
				elif( isinstance( _bone, bones.baseBone ) ):
					res[key] = _bone.value
		return res
		
	def view( self, skel, listname="view", *args, **kwargs ):
		res = {	"values": self.renderSkelValues( skel ), 
				"structure": self.renderSkelStructure( skel ) }
		return( json.dumps( res ) )
		
	def add( self, skel, **kwargs ):
		return( self.view( skel ) )

	def edit( self, skel, **kwargs ):
		return( self.view( skel ) )

	def list( self, skellist, **kwargs ):
		res = {}
		skels = []
		for skel in skellist:
			skels.append( self.renderSkelValues( skel ) )
		res["skellist"] = skels
		if( len( skellist )>0 ):
			res["structure"] = self.renderSkelStructure( skellist[0] )
		else:
			res["structure"] = None
		res["cursor"] = skellist.cursor
		return( json.dumps( res ) )

	def editItemSuccess(self, *args, **kwargs ):
		return( json.dumps("OKAY") )
		
	def addItemSuccess(self, *args, **kwargs ):
		return( json.dumps("OKAY") )
		
	def deleteItemSuccess(self, *args, **kwargs ):
		return( json.dumps("OKAY") )

	def addDirSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )

	def listRootNodes(self, rootNodes ):
		return( json.dumps( rootNodes ) )
		
	def listRootNodeContents(self, subdirs, entrys, **kwargs ):
		res = { "subdirs": subdirs }
		skels = []
		for skel in entrys:
			skels.append( self.renderSkelValues( skel ) )
		res["entrys"] = skels
		return( json.dumps( res ) )
	
	def renameSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )

	def copySuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )

	def deleteSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )

	def reparentSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )

	def setIndexSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )
