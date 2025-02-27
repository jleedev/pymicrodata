# -*- coding: utf-8 -*-
"""
This module implements the microdata->RDF algorithm, as documented by the U{W3C Semantic Web Interest Group
Note<http://www.w3.org/TR/2012/NOTE-microdata-rdf-20141216/>}.

The module can be used via a stand-alone script (an example is part of the distribution) or bound to a CGI script as a
Web Service. An example CGI script is also added to the distribution. Both the local script and the distribution may
have to be adapted to local circumstances.

(Simple) Usage
==============
From a Python file, expecting a Turtle output::
 from pyMicrodata import pyMicrodata
 print pyMicrodata().rdf_from_source('filename')
Other output formats are also possible. E.g., to produce RDF/XML output, one could use::
 from pyMicrodata import pyMicrodata
 print pyMicrodata().rdf_from_source('filename', output_format='pretty-xml')
It is also possible to embed an RDFa processing. Eg, using::
 from pyMicrodata import pyMicrodata
 graph = pyMicrodata().graph_from_source('filename')
returns an RDFLib.Graph object instead of a serialization thereof. See the the description of the
L{pyMicrodata class<pyMicrodata.pyMicrodata>} for further possible entry points details.

There is also, as part of this module, a L{separate entry for CGI calls<processURI>}.

Return formats
--------------

By default, the output format for the graph is RDF/XML. At present, the following formats are also available (with the
corresponding key to be used in the package entry points):

 - "xml": U{RDF/XML<http://www.w3.org/TR/rdf-syntax-grammar/>}
 - "turtle": U{Turtle<http://www.w3.org/TR/turtle/>} (default)
 - "nt": U{N-triple<http://www.w3.org/TR/rdf-testcases/#ntriples>}
 - "json": U{JSON-LD<http://json-ld.org/spec/latest/json-ld-syntax/>}

@summary: Microdata parser (distiller)
@requires: Python version 3.5 or up
@requires: U{RDFLib<http://rdflib.net>}
@requires: U{html5lib<http://code.google.com/p/html5lib/>} for the HTML5 parsing; note possible dependecies on Python's
            version on the project's web site
@organization: U{World Wide Web Consortium<http://www.w3.org>}
@author: U{Ivan Herman<http://www.w3.org/People/Ivan/>}
@license: This software is available for use under the
U{W3C® SOFTWARE NOTICE AND LICENSE<href="http://www.w3.org/Consortium/Legal/2002/copyright-software-20021231">}
"""

"""
$Id: __init__.py,v 1.17 2014-12-17 08:52:43 ivan Exp $ $Date: 2014-12-17 08:52:43 $
"""

__version__ = "2.1"
__author__ = "Ivan Herman"
__contact__ = "Ivan Herman, ivan@w3.org"
__all__ = ["pyMicrodata", "HTTPError", "MicrodataError"]

name = "pyMicrodata"

import sys
from io import StringIO
import datetime
from rdflib import URIRef
from rdflib import Literal
from rdflib import BNode
from rdflib import Namespace
from rdflib import Graph
from rdflib.namespace import RDF, XSD, SKOS, FOAF, DCTERMS, RDFS
from urllib.parse import urlparse
from .utils import URIOpener
from .microdata import MicrodataConversion

debug = False

ns_micro = Namespace("http://www.w3.org/2012/pyMicrodata/vocab#")
ns_ht = Namespace("http://www.w3.org/2006/http#")


class MicrodataError(Exception):
    """Superclass exceptions representing error conditions defined by the RDFa 1.1 specification.
    It does not add any new functionality to the Exception class."""

    def __init__(self, msg):
        self.msg = msg
        Exception.__init__(self)


class HTTPError(MicrodataError):
    """Raised when HTTP problems are detected. It does not add any new functionality to the
    Exception class."""

    def __init__(self, http_msg, http_code):
        self.msg = http_msg
        self.http_code = http_code
        MicrodataError.__init__(self, http_msg)


# Default bindings. This is just for the beauty of things: bindings are added to the graph to make the output nicer.
# If this is not done, RDFlib defines prefixes like "_1:", "_2:" which is, though correct, ugly...

_bindings = {
    "gr": "http://purl.org/goodrelations/v1#",
    "cc": "http://creativecommons.org/ns#",
    "sioc": "http://rdfs.org/sioc/ns#",
    "skos": SKOS,
    "rdfs": RDFS,
    "foaf": FOAF,
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "rdf": RDF,
    "xsd": XSD,
}


#########################################################################################################
class pyMicrodata:
    """Main processing class for the distiller
    @ivar base: the base value for processing
    @ivar http_status: HTTP Status, to be returned when the package is used via a CGI entry. Initially set to 200,
            may be modified by exception handlers
    """

    def __init__(self, base=""):
        """
        @keyword base: URI for the default "base" value (usually the URI of the file to be processed)
        """
        self.http_status = 200
        self.base = base

    def _generate_error_graph(self, pgraph, full_msg, uri=None):
        """
        Generate an error message into the graph. This method is usually used reacting on exceptions.

        Later versions of pyMicrodata may have more detailed error conditions on which it wishes to react. At the
        moment, this is fairly crude...
        """
        if pgraph is None:
            retval = Graph()
        else:
            retval = pgraph

        pgraph.bind("dc", DCTERMS)
        pgraph.bind("xsd", XSD)
        pgraph.bind("ht", "http://www.w3.org/2006/http#")
        pgraph.bind("pyMicrodata", "http://www.w3.org/2012/pyMicrodata/vocab#")

        bnode = BNode()
        retval.add((bnode, RDF.type, ns_micro["Error"]))
        retval.add((bnode, DCTERMS.description, Literal(full_msg)))
        retval.add(
            (
                bnode,
                DCTERMS.date,
                Literal(datetime.datetime.utcnow().isoformat(), datatype=XSD.dateTime),
            )
        )

        if uri is not None:
            htbnode = BNode()
            retval.add((bnode, ns_micro["context"], htbnode))
            retval.add((htbnode, RDF.type, ns_ht["Request"]))
            retval.add((htbnode, ns_ht["requestURI"], Literal(uri)))

        if self.http_status is not None and self.http_status != 200:
            htbnode = BNode()
            retval.add((bnode, ns_micro["context"], htbnode))
            retval.add((htbnode, RDF.type, ns_ht["Response"]))
            retval.add(
                (
                    htbnode,
                    ns_ht["responseCode"],
                    URIRef("http://www.w3.org/2006/http#%s" % self.http_status),
                )
            )

        return retval

    def _get_input(self, name_):
        """
        Trying to guess whether "name" is a URI, a string; it then tries to open these as such accordingly,
        returning a file-like object. If name is a plain string then it returns the input argument (that should
        be, supposedly, a file-like object already)
        @param name_: identifier of the input source
        @type name_: string or a file-like object
        @return: a file like object if opening "name" is possible and successful, "name" otherwise
        """
        if isinstance(name_, str):
            # check if this is a URI, ie, if there is a valid 'scheme' part
            # otherwise it is considered to be a simple file
            if urlparse(name_)[0] != "":
                url_request = URIOpener(name_)
                self.base = url_request.location
                return url_request.data
            else:
                self.base = "file://" + name_
                return open(name_, "rb")
        else:
            return name_

    @staticmethod
    def _validate_output_format(outputFormat):
        """
        Malicious actors may create XSS style issues by using an illegal output format... better be careful
        """
        # protection against possible malicious URL call
        if outputFormat not in ["turtle", "n3", "xml", "pretty-xml", "nt", "json-ld"] :
            outputFormat = "turtle"
        return outputFormat

    ####################################################################################################################
    # Externally used methods
    #
    def graph_from_dom(self, dom, graph=None):
        """
        Extract the RDF Graph from a DOM tree.
        @param dom: a DOM Node element, the top level entry node for the whole tree (to make it clear, a
        dom.documentElement is used to initiate processing)
        @keyword graph: an RDF Graph (if None, than a new one is created)
        @type graph: rdflib Graph instance. If None, a new one is created.
        @return: an RDF Graph
        @rtype: rdflib Graph instance
        """
        if graph is None:
            # Create the RDF Graph, that will contain the return triples...
            graph = Graph()

        conversion = MicrodataConversion(dom.documentElement, graph, base=self.base)
        conversion.convert()
        return graph

    def graph_from_source(self, name_, graph=None, rdf_output=False):
        """
        Extract an RDF graph from an microdata source. The source is parsed, the RDF extracted, and the RDF Graph is
        returned. This is a front-end to the L{pyMicrodata.graph_from_DOM} method.

        @param name_: a URI, a file name, or a file-like object
        @return: an RDF Graph
        @rtype: rdflib Graph instance
        """
        # First, open the source...
        try:
            # First, open the source... Possible HTTP errors are returned as error triples
            input = None
            try:
                input = self._get_input(name_)
            except HTTPError:
                h = sys.exc_info()[1]
                self.http_status = h.http_code
                if not rdf_output:
                    raise h
                return self._generate_error_graph(
                    graph, "HTTP Error: %s (%s)" % (h.http_code, h.msg), uri=name_
                )
            except Exception:
                # Something nasty happened:-(
                e = sys.exc_info()[1]
                self.http_status = 500
                if not rdf_output:
                    raise e
                return self._generate_error_graph(graph, str(e), uri=name_)

            dom = None
            try:
                import warnings

                warnings.filterwarnings("ignore", category=DeprecationWarning)
                import html5lib

                parser = html5lib.HTMLParser(
                    tree=html5lib.treebuilders.getTreeBuilder("dom")
                )
                dom = parser.parse(input)
                return self.graph_from_dom(dom, graph)
            except ImportError:
                msg = "HTML5 parser not available. Try installing html5lib <http://code.google.com/p/html5lib>"
                raise ImportError(msg)
            except Exception:
                # Something nasty happened:-(
                e = sys.exc_info()[1]
                self.http_status = 400
                if not rdf_output:
                    raise e
                return self._generate_error_graph(graph, str(e), uri=name_)

        except Exception:
            # Something nasty happened:-(
            e = sys.exc_info()[1]
            if isinstance(e, ImportError):
                self.http_status = None
            else:
                self.http_status = 500
            if not rdf_output:
                raise e
            return self._generate_error_graph(graph, str(e), uri=name_)

    def rdf_from_sources(self, names, output_format="turtle", rdf_output=False):
        """
        Extract and RDF graph from a list of RDFa sources and serialize them in one graph. The sources are parsed, the
        RDF extracted, and serialization is done in the specified format.

        @param names: list of sources, each can be a URI, a file name, or a file-like object
        @type names: list
        @param output_format: serialization format. Can be one of "turtle", "n3", "xml", "pretty-xml", "nt". "xml"
                and "pretty-xml", as well as "turtle" and "n3" are synonyms.
        @type output_format: string
        @param rdf_output: output from internal processes
        @type rdf_output: string
        @return: a serialized RDF Graph
        @rtype: string
        """
        graph = Graph()

        for prefix in _bindings:
            graph.bind(prefix, Namespace(_bindings[prefix]))

        # the value of rdfOutput determines the reaction on exceptions...
        for name in names:
            self.graph_from_source(name, graph, rdf_output)
        return str(graph.serialize(format=output_format), encoding="utf-8")

    def rdf_from_source(self, name_, output_format="turtle", rdf_output=False):
        """
        Extract and RDF graph from an RDFa source and serialize it in one graph. The source is parsed, the RDF
        extracted, and serialization is done in the specified format.

        @param name_: a URI, a file name, or a file-like object
        @type name_:
        @param output_format: serialization format. Can be one of "turtle", "n3", "xml", "pretty-xml", "nt". "xml" and
                "pretty-xml", as well as "turtle" and "n3" are synonyms.
        @type output_format: string
        @param rdf_output: output from internal processes
        @type rdf_output: string
        @return: a serialized RDF Graph
        @rtype: string
        """
        return self.rdf_from_sources([name_], output_format, rdf_output)


# ################################################ CGI Entry point
def process_uri(uri, output_format, form):
    """The standard processing of a microdata uri options in a form, ie, as an entry point from a CGI call.

    The call accepts extra form options (eg, HTTP GET options) as follows:

    @param uri: URI to access. Note that the "text:" and "uploaded:" values are treated separately; the former is for
                textual intput (in which case a StringIO is used to get the data) and the latter is for uploaded file,
                where the form gives access to the file directly.
    @param output_format: serialization formats, as understood by RDFLib. Note that though "turtle" is
    a possible parameter value, some versions of the RDFLib turtle generation does funny (though legal) things with
    namespaces, defining unusual and unwanted prefixes...
    @param form: extra call options (from the CGI call) to set up the local options (if any)
    @type form: cgi FieldStorage instance
    @return: serialized graph
    @rtype: string
    """
    if uri == "uploaded:":
        input = form["uploaded"].file
        base = ""
    elif uri == "text:":
        input = StringIO(form.getfirst("text"))
        base = ""
    else:
        input = uri
        base = uri

    processor = pyMicrodata(base=base)

    # Decide the output format; the issue is what should happen in case of a top level error like an inaccessibility of
    # the html source: should a graph be returned or an HTML page with an error message?

    # decide whether HTML or RDF should be sent.
    htmlOutput = False
    # import os
    # if 'HTTP_ACCEPT' in os.environ :
    # 	acc = os.environ['HTTP_ACCEPT']
    # 	possibilities = ['text/html',
    # 					 'application/rdf+xml',
    # 					 'text/turtle; charset=utf-8',
    # 					 'application/json',
    # 					 'application/ld+json',
    # 					 'text/rdf+n3']
    #
    # 	# this nice module does content negotiation and returns the preferred format
    # 	sg = httpheader.acceptable_content_type(acc, possibilities)
    # 	htmlOutput = (sg != None and sg[0] == httpheader.content_type('text/html'))
    # 	os.environ['rdfaerror'] = 'true'

    try:
        outputFormat = pyMicrodata._validate_output_format(outputFormat);
        if output_format == "n3":
            retval = "Content-Type: text/rdf+n3; charset=utf-8\n"
        elif output_format == "nt" or output_format == "turtle":
            retval = "Content-Type: text/turtle; charset=utf-8\n"
        elif output_format == "json-ld" or output_format == "json":
            retval = "Content-Type: application/ld+json; charset=utf-8\n"
        else:
            retval = "Content-Type: application/rdf+xml; charset=utf-8\n"
        graph = processor.rdf_from_source(
            input,
            output_format,
            rdf_output=("forceRDFOutput" in list(form.keys())) or not htmlOutput,
        )
        retval += "\n"
        retval += graph
        return retval
    except HTTPError:
        import cgi

        h = sys.exc_info()[1]
        retval = "Content-type: text/html; charset=utf-8\nStatus: %s \n\n" % h.http_code
        retval += "<html>\n"
        retval += "<head>\n"
        retval += "<title>HTTP Error in Microdata processing</title>\n"
        retval += "</head><body>\n"
        retval += "<h1>HTTP Error in distilling Microdata</h1>\n"
        retval += "<p>HTTP Error: %s (%s)</p>\n" % (h.http_code, h.msg)
        retval += "<p>On URI: <code>'%s'</code></p>\n" % cgi.escape(uri)
        retval += "</body>\n"
        retval += "</html>\n"
        return retval
    except:
        # This branch should occur only if an exception is really raised, ie, if it is not turned
        # into a graph value.
        (type, value, traceback) = sys.exc_info()

        import traceback, cgi

        retval = (
            "Content-type: text/html; charset=utf-8\nStatus: %s\n\n"
            % processor.http_status
        )
        retval += "<html>\n"
        retval += "<head>\n"
        retval += "<title>Exception in Microdata processing</title>\n"
        retval += "</head><body>\n"
        retval += "<h1>Exception in distilling Microdata</h1>\n"
        retval += "<pre>\n"
        strio = StringIO()
        traceback.print_exc(file=strio)
        retval += strio.getvalue()
        retval += "</pre>\n"
        retval += "<pre>%s</pre>\n" % value
        retval += "<h1>Distiller request details</h1>\n"
        retval += "<dl>\n"
        if (
            uri == "text:"
            and "text" in form
            and form["text"].value is not None
            and len(form["text"].value.strip()) != 0
        ):
            retval += "<dt>Text input:</dt><dd>%s</dd>\n" % cgi.escape(
                form["text"].value
            ).replace("\n", "<br/>")
        elif uri == "uploaded:":
            retval += "<dt>Uploaded file</dt>\n"
        else:
            retval += "<dt>URI received:</dt><dd><code>'%s'</code></dd>\n" % cgi.escape(
                uri
            )
        retval += "<dt>Output serialization format:</dt><dd> %s</dd>\n" % output_format
        retval += "</dl>\n"
        retval += "</body>\n"
        retval += "</html>\n"

    return retval


# ##################################################################################################
