# -*- coding: utf-8 -*-
import json
from server import bones
from collections import OrderedDict
from server import errors, request

class DefaultRender( object ):
	
	def __init__(self, parent=None, *args, **kwargs ):
		super( DefaultRender,  self ).__init__( *args, **kwargs )
		self.parent = parent
	
	def renderSkelStructure(self, skel ):
		"""Dumps the Structure of a Skeleton"""
		if isinstance( skel, dict ):
			return( None )
		res = OrderedDict()
		for key, _bone in skel.items() :
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
				elif any( [x.startswith("%s." % key) for x in skel.errors.keys()]):
					res[ key ][ "error" ] = {k:v for k,v in skel.errors.items() if k.startswith("%s." % key )}
				else:
					res[ key ][ "error" ] = None
				if isinstance( _bone, bones.relationalBone ):
					if isinstance( _bone, bones.hierarchyBone ):
						boneType = "hierarchy"
					elif isinstance( _bone, bones.treeItemBone ):
						boneType = "treeitem"
					else:
						boneType = "relational"
						if _bone.using is not None:
							res[key]["using"] = self.renderSkelStructure(_bone.using())
						else:
							res[key]["using"] = None
					res[key]["type"]="%s.%s" % (boneType,_bone.type)
					res[key]["module"] = _bone.module
					res[key]["multiple"]=_bone.multiple
					res[key]["format"] = _bone.format
				if( isinstance( _bone, bones.treeDirBone ) ):
						boneType = "treedir"
						res[key]["type"]="%s.%s" % (boneType,_bone.type)
						res[key]["multiple"]=_bone.multiple
				if ( isinstance( _bone, bones.selectOneBone ) or  isinstance( _bone, bones.selectMultiBone ) ):
					res[key]["values"] = dict( [(k,_(v)) for (k,v) in _bone.values.items() ] )
					#res[key]["valuesOrder"] = _bone.valuesOrder
					#res[key]["sortBy"] = _bone.sortBy
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
				if( isinstance( _bone, bones.textBone ) ) or ( isinstance( _bone, bones.stringBone ) ):
					res[key]["languages"] = _bone.languages
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
		for key,_bone in skel.items():
			if isinstance( _bone, bones.dateBone ):
				if _bone.value:
					if _bone.date and _bone.time:
						res[key] = _bone.value.strftime("%d.%m.%Y %H:%M:%S")
					elif _bone.date:
						res[key] = _bone.value.strftime("%d.%m.%Y")
					else:
						res[key] = _bone.value.strftime("%H:%M:%S")
			elif( isinstance(_bone, bones.relationalBone)):
				if isinstance(_bone.value, list):
					tmpList = []
					for k in _bone.value:
						tmpList.append({"dest": self.renderSkelValues(k["dest"]),
				                        "rel": self.renderSkelValues(k["rel"]) if k["rel"] else None})
					res[key] = tmpList
				elif isinstance(_bone.value, dict):
					res[key] = {"dest": self.renderSkelValues(_bone.value["dest"]),
					            "rel": self.renderSkelValues(_bone.value["rel"]) if _bone.value["rel"] else None}
			elif( isinstance( _bone, bones.baseBone ) ):
				res[key] = _bone.value
		return res
		
	def renderEntry( self, skel, actionName ):
		if isinstance( skel, list ):
			vals = [ self.renderSkelValues( x ) for x in skel ]
			struct = self.renderSkelStructure( skel[0] )
		else:
			vals = self.renderSkelValues( skel )
			struct = self.renderSkelStructure( skel )
		res = {	"values": vals, 
			"structure": struct,
			"action": actionName }
		request.current.get().response.headers['Content-Type'] = "application/json"
		return( json.dumps( res ) )

	
	def view( self, skel, listname="view", *args, **kwargs ):
		return( self.renderEntry( skel, "view" ) )
		
	def add( self, skel, **kwargs ):
		return( self.renderEntry( skel, "add" ) )

	def edit( self, skel, **kwargs ):
		return( self.renderEntry( skel, "edit" ) )

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
		res["action"] = "list"
		request.current.get().response.headers['Content-Type'] = "application/json"
		return( json.dumps( res ) )

	def editItemSuccess(self, skel, **kwargs ):
		return( self.renderEntry( skel, "editSuccess" ) )
		
	def addItemSuccess(self, skel, **kwargs ):
		return( self.renderEntry( skel, "addSuccess" ) )
		
	def deleteItemSuccess(self, skel, **kwargs ):
		return( self.renderEntry( skel, "deleteSuccess" ) )

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

	def cloneSuccess(self, *args, **kwargs ):
		return( json.dumps( "OKAY") )