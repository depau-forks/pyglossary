# -*- coding: utf-8 -*-

from pyglossary.plugins.formats_common import *
from pyglossary.html_utils import unescape_unicode
from io import BytesIO

enable = True
lname = "iupac_goldbook"
format = "IUPACGoldbook"
description = "IUPAC goldbook (.xml)"
extensions = ()
extensionCreate = ".xml"
singleFile = True
kind = "text"
wiki = ""
website = "https://goldbook.iupac.org/"
optionsProp = {}


class Reader(object):

	compressions = stdCompressions
	depends = {
		"lxml": "lxml",
	}

	def __init__(self, glos: "GlossaryType") -> None:
		self._glos = glos
		self._filename = ""
		self._file = None
		self._fileSize = 0
		self._termByCode = None

	def __len__(self) -> int:
		return 0

	def close(self) -> None:
		if self._file:
			self._file.close()
			self._file = None
		self._filename = ""
		self._fileSize = 0
		self._termByCode = None

	def open(self, filename) -> None:
		try:
			from lxml import etree as ET
		except ModuleNotFoundError as e:
			e.msg += f", run `{pip} install lxml` to install"
			raise e

		self._filename = filename
		_file = compressionOpen(filename, mode="rb")
		_file.seek(0, 2)
		self._fileSize = _file.tell()
		_file.seek(0)

		chunk = _file.read(800)
		chunk_end = chunk.find(b"<entries>")
		chunk = chunk[:chunk_end]
		chunk += b"</vocabulary>"

		infoRoot = ET.fromstring(chunk)
		self.setMetadata(infoRoot)

		_file.seek(0)
		context = ET.iterparse(
			_file,
			events=("end",),
			tag=f"entry",
		)
		termByCode = {}
		for action, elem in context:
			termE = elem.find("./term")
			if termE is None:
				continue
			term = self.getTerm(termE)
			codeE = elem.find("./code")
			if codeE is None:
				continue
			termByCode[codeE.text] = term
		self._termByCode = termByCode

		_file.close()

	def setGlosInfo(self, key: str, value: str) -> None:
		if value is None:
			return
		self._glos.setInfo(key, unescape_unicode(value))

	def setMetadata(self, header):
		self.setGlosInfo("name", header.find("./title").text)
		self.setGlosInfo("publisher", header.find("./publisher").text)
		self.setGlosInfo("isbn", header.find("./isbn").text)
		self.setGlosInfo("doi", header.find("./doi").text)
		self.setGlosInfo("creationTime", header.find("./accessdate").text)

	def tostring(self, elem: "lxml.etree.Element") -> str:
		from lxml import etree as ET
		return ET.tostring(
			elem,
			method="html",
			pretty_print=True,
		).decode("utf-8").strip()

	def innerXML(self, elem):
		from lxml import etree as ET
		elemName = elem.xpath('name(/*)')
		resultStr = ''
		for e in elem.xpath('/'+ elemName + '/node()'):
			if(isinstance(e, str) ):
				resultStr = resultStr + ''
			else:
				resultStr = resultStr + ET.tostring(e, encoding='unicode')

		return resultStr

	def getTerm(self, termE):
		from lxml import etree as ET
		term = ET.tostring(
			termE,
			method="html",
			pretty_print=False,
		).decode("utf-8").strip()[6:-7].strip()
		term = unescape_unicode(term)
		term = term.replace("<i>", "").replace("</i>", "")
		return term

	def __iter__(self) -> "Iterator[BaseEntry]":
		from lxml import etree as ET

		glos = self._glos
		fileSize = self._fileSize
		termByCode = self._termByCode

		self._file = _file = compressionOpen(self._filename, mode="rb")
		context = ET.iterparse(
			self._file,
			events=("end",),
			tag=f"entry",
		)
		for action, elem in context:
			codeE = elem.find("./code")
			if codeE is None:
				continue
			code = codeE.text

			_id = elem.attrib.get("id")
			termE = elem.find("./term")
			if termE is None:
				log.warning(f"no term, code={code}, id={_id}")
				continue

			term = self.getTerm(termE)

			words = []
			if term:
				words.append(term)
			if code:
				words.append(code)

			#if _id is not None:
			#	words.append(f"id{_id}")

			identifierTerm = elem.find("./identifiers/term")
			if identifierTerm is not None and identifierTerm.text:
				words.append(identifierTerm.text)

			identifierSynonym = elem.find("./identifiers/synonym")
			if identifierSynonym is not None and identifierSynonym.text:
				words.append(identifierSynonym.text)

			defiParts = []

			definition = elem.find("./definition")
			if definition is None or not definition.text:
				pass
			else:
				defiParts.append(definition.text)

			definitionEntryList = elem.findall("./definition/entry")
			if definitionEntryList:
				bio = BytesIO()
				with ET.htmlfile(bio, encoding="utf-8") as hf:
					with hf.element("ol"):
						for item in definitionEntryList:
							if not item.text:
								continue
							with hf.element("li"):
								hf.write(item.text)
				listHtml = bio.getvalue().decode("utf-8")
				defiParts.append(listHtml)

			replacedbyE = elem.find("./replacedby")
			if replacedbyE is not None:
				replacedby = replacedbyE.text
				replacedbyCode = replacedby.split(".")[-1]
				replacedbyTerm = termByCode.get(replacedbyCode)
				if replacedbyTerm is None:
					log.warning(f"{term}: replacedby={replacedby}")
					replacedbyTerm = replacedbyCode
				defiParts.append(
					f'Replaced by: <a href="bword://{replacedbyTerm}">{replacedbyTerm}</a>'
				)
			
			relatedList = elem.findall("./related/entry")
			if relatedList:
				relatedLinkList = []
				for related in relatedList:
					relatedURL = related.text
					relatedCode = relatedURL.split("/")[-1]
					relatedTerm = termByCode.get(relatedCode)
					if not relatedTerm:
						log.warning(f"{term}: related={relatedURL}")
						relatedTerm = relatedCode
					relatedLinkList.append(
						f'<a href="bword://{relatedTerm}">{relatedTerm}</a>'
					)
				defiParts.append("Related: " + ", ".join(relatedLinkList))

			lastupdatedE = elem.find("./lastupdated")
			if lastupdatedE is not None:
				defiParts.append(f"Last updated: {lastupdatedE.text}")

			urlE = elem.find("./url")
			if urlE is not None:
				defiParts.append(f'<a href="{urlE.text}">More info.</a>')

			if len(defiParts) > 1:
				defiParts.insert(1, "")

			try:
				defi = "<br/>".join(defiParts)
			except Exception:
				log.error(f"defiParts = {defiParts!r}")
				continue

			yield glos.newEntry(
				words,
				defi,
				defiFormat="h",
				byteProgress=(_file.tell(), fileSize),
			)

			# clean up preceding siblings to save memory
			# this can reduce memory usage from >300 MB to ~25 MB
			while elem.getprevious() is not None:
				del elem.getparent()[0]
