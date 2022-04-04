from django.shortcuts import render
from django.http import HttpResponse
import pandas as pd
from django.http import HttpResponse
import datetime
import subprocess
import os
import socket
import re
import requests
import urllib.request
from django.views.decorators.clickjacking import xframe_options_exempt		# To allow certain pages to be inserted as iframes in other pages
from bs4 import BeautifulSoup
from .parse_merge_pacs_ea_notifications import get_all_merge_pacs_metrics
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from pydicom import config

from pynetdicom import (
        AE, 
        BasicWorklistManagementPresentationContexts,
        debug_logger
)

from pynetdicom.sop_class import ModalityWorklistInformationFind

import logging

from datetime import datetime

# Create your views here.

def home(request):
    return render(request, 'index.html')



# Test of outputting metrics for Prometheus
def metrics(request):
    response_list = None
    response_list = get_all_merge_pacs_metrics()
    newline = '\n'
    return HttpResponse(newline.join(response_list), content_type = 'text/plain')

def getHost(ip):
    """
    This method returns the 'True Host' name for a
    given IP address
    """
    try:
        data = socket.gethostbyaddr(ip)
        host = repr(data[0])
        return host
    except Exception:
        # fail gracefully
        return False

@xframe_options_exempt
def pacs(request):
    response_list = []
    x = "medimgarchive.healthpartners.com"
    y = "pacsprod.healthpartners.com"
    #caluclation
    ea_fqdn_peera = "'mergeeapri.healthpartners.com'"
    mergepacs_fqdn_peera = "'mergepacsprd.healthpartners.com'"
    ea_fqdn_peerb = "'mergeeasec.healthpartners.com'"
    mergepacs_fqdn_peerb = "'mergepacscnt.healthpartners.com'"

    active_ea_hostname = getHost(x)
    active_mergepacs_hostname = getHost(y)

    # Get current active EA peer
    if active_ea_hostname == ea_fqdn_peera :
        ea_active_peer = "A"
        ea_inactive_peer = "B"
        ea_inactive_fqdn = ea_fqdn_peerb
    elif active_ea_hostname == ea_fqdn_peerb :
        ea_active_peer = "B"
        ea_inactive_peer = "A"
        ea_inactive_fqdn = ea_fqdn_peera
    else:
        response_list.append(f'ERROR finding EA peer')

    # Get current active Merge PACS peer
    if active_mergepacs_hostname == mergepacs_fqdn_peera :
        mergepacs_active_peer = "A"
        mergepacs_inactive_peer = "B"
        mergepacs_inactive_fqdn = mergepacs_fqdn_peerb
    elif active_mergepacs_hostname == mergepacs_fqdn_peerb :
        mergepacs_active_peer = "B"
        mergepacs_inactive_peer = "A"
        mergepacs_inactive_fqdn = mergepacs_fqdn_peera
    else:
        response_list.append(f'ERROR finding active mergepacs peer')


    #print Results in format
    response_list.append(f'The current ACTIVE EA and Merge PACS systems for this environment are')
    response_list.append(f'EA : {ea_active_peer}  ({active_ea_hostname})')
    response_list.append(f'MergePACS : {mergepacs_active_peer}  ({active_mergepacs_hostname})')
    response_list.append('\n')
    response_list.append(f'The current INACTIVE EA and Merge PACS systems for this environment are')
    response_list.append(f'EA : {ea_inactive_peer} ({ea_inactive_fqdn})')
    response_list.append(f'MergePACS : {mergepacs_inactive_peer} ({mergepacs_inactive_fqdn})')
    newline = '\n'
    return HttpResponse(newline.join(response_list), content_type = 'text/plain')

def recurse(dataset, level=0, parent_tags = ''):
    
    dont_print = ['Pixel Data', 'File Meta Information Version']
    
    recurse_output = []

    indent_string = "  " * level
    next_indent_string = "  " * (level + 1)

    parent_tags_string = parent_tags

    for data_element in dataset:
        #next_parent_tags_string = f"parent_tags_string\\{data_element.tag}"
        
        # If the element is a sequence of subelements...
        if data_element.VR == 'SQ':     # a sequence of sub-elements or sub-sequences
            #elem_as_text = data_element.__str__()
            #print_line = f"{elem_as_text}"

            str_data_element = str(data_element)
            
            msg = f"%% {indent_string}{str_data_element}"
            recurse_output.append(msg)
            #print("%% ", indent_string, data_element, sep='')
            next_parent_tags_string = f"{parent_tags}{data_element.tag}\\"

            sequence_name = data_element.name

            for sequence_item in data_element.value:
                output_msgs_list = recurse(sequence_item, level + 1, next_parent_tags_string)
                recurse_output.extend(output_msgs_list)

                msg = "%% " + next_indent_string + "---- End of " + sequence_name + "----"
                recurse_output.append(msg)
        else:
            if data_element.name in dont_print:
                # do nothing
                pass
            else:
                repr_value = repr(data_element.value)   # printable representation of value (in case it's an object?)
                msg = f"%% {indent_string}{parent_tags_string}{data_element.tag} {data_element.name} ({data_element.VR})= {repr_value}"
                recurse_output.append(msg)
                
                #elem_as_text = data_element.__str__()
                #print_line = f"{indent_string}{elem_as_text}"
                #recurse_output.append(print_line)
                #print("%% ",padding,parent_tags_string,elem,sep="")
    #print(recurse_output)
    return recurse_output

def create_mwl_query_dataset():
    # Create our Identifier (query) dataset
    ds = Dataset()
    ds.AccessionNumber = ''                                 # 0008,0050
    ds.ReferringPhysicianName = ''                          # 0008,0090
    ds.PatientName = ''                           # Tag (0010,0010)
    ds.PatientID = ''                                       # (0010,0020)
    ds.PatientBirthDate = ''                                # (0010,0030)
    ds.PatientSex = ''                                      # (0010,0040)
    ds.StudyInstanceUID = ''                                # (0020,000D)
    ds.RequestingPhysician = ''                             # (0032,1032)
    ds.RequestedProcedureDescription = ''                   # (0032,1060)
    ds.RequestedProcedureCodeSequence = ''                  # (0032,1064)
    ds.CurrentPatientLocation = ''                          # (0038,0300)
    # Create Scheduled Procedure Start Set sequence (as a sub-object of the query dataset)
    ds.ScheduledProcedureStepSequence = [Dataset()]
    spss = ds.ScheduledProcedureStepSequence[0]
    spss.Modality = ''
    spss.ScheduledStationAETitle = ''
    spss.ScheduledProcedureStepStartDate = datetime.today().strftime('%Y%m%d') #Default to "today" in yyyymmdd format
    spss.ScheduledProcedureStepStartTime = ''
    spss.ScheduledPerformingPhysicianName = ''
    spss.ScheduledProcedureStepDescription = ''
    spss.ScheduledProtocolCodeSequence = ''

    return(ds)

def execute_mwl_query(TargetServer, MWLQueryCriteria=create_mwl_query_dataset()):

    output_text = []
    response_datasets_arr = []      # Array with 'identifier' dataset objects with query results

    #    
    # Set default values for MWL query (these should really be set by the user in a GUI
    #
    patient_name = '*'
    calling_ae_title = 'rgns-ct3'               # The "local" AE Title -- in other words, the device we're impersonating
    scheduled_station_aetitle = ''      # Usually we don't use this
    scheduled_procedure_step_startdate = datetime.today().strftime('%Y%m%d') #Default to "today" in yyyymmdd format
    modality = 'CT'
    
    #
    # Set default values for MWL server association information (these should also really be set by the user in a GUI)
    #
    mwl_hostname =  TargetServer
    #mwl_hostname =  'epicmwl.healthpartners.com'         # Hostname or IP for the MWL server
    mwl_port =      52000                  # DICOM MWL server port
    mwl_ae_title =  b'EPICRADIANT'      # AE title for MWL SCP (the MWL server)
    
    
    LOGGER = logging.getLogger('pynetdicom')
    LOGGER.setLevel(logging.DEBUG)  #Set logging to show ALL information DEBUG and above
    # Print debugging info
    #debug_logger()


    # Prompt user for query values
    #patient_name = input("Enter a patient name to search for [*]: ")
    #if patient_name == '':
    #    patient_name = '*'


    # Create a new query dataset based on the defined class
    MWLQueryCriteria = create_mwl_query_dataset()

    # Set some of the values in the query
    MWLQueryCriteria.PatientName = patient_name
    MWLQueryCriteria.calling_ae_title = calling_ae_title
    MWLQueryCriteria.scheduled_station_aetitle = scheduled_station_aetitle
    # Already defaults to today: ds.scheduled_procedure_step_startdate = datetime.today().strftime('%Y%m%d') #Default to "today" in yyyymmdd format
    MWLQueryCriteria.ScheduledProcedureStepSequence[0].Modality = modality

    output_text.append("Query dataset:")

    mwl_query_as_text = MWLQueryCriteria.__str__()
    output_text.append(mwl_query_as_text)

    # Capture timing info
    start_time = datetime.now()

    # Initialise the Application Entity
    ae = AE()

    # Add a requested presentation context
    ae.add_requested_context(ModalityWorklistInformationFind)

    # Set Calling AE Title
    ae.ae_title = calling_ae_title
    output_text.append("Calling AE Title: " + calling_ae_title)

    # Associate with peer AE (hostname, port, remote AE Title)
    assoc = ae.associate(mwl_hostname, mwl_port, ae_title=mwl_ae_title)

    if assoc.is_established:
        association_complete_time = datetime.now()

        # Use the C-FIND service to send the identifier
        responses = assoc.send_c_find(
            MWLQueryCriteria,
            ModalityWorklistInformationFind
        )

        results_count = 0

        for (status, identifier) in responses:
            if status:
                msg = 'C-FIND query status: 0x{0:04x}'.format(status.Status)
                output_text.append(msg)

                # If the status is 'Pending' then identifier is the C-FIND response (a DICOM Dataset)
                if status.Status in (0xFF00, 0xFF01):
                    #print(identifier)
                    response_strings_arr = recurse(identifier)      # returns array of strings with output
                    response_datasets_arr.append(identifier)        # Add identifier (valid response) objects to an array of results objects
                    output_text.extend(response_strings_arr)          # Add results array to the end of the current array of output text
                    #for elem in identifier:
                        #print("Element: ", elem)
                        #print("     ",elem.name,":",elem._value)
                        #print_element(elem)
                        #pass  
                elif status.Status == 0x0000:
                    msg = f"End of results. Total results found: {results_count}"
                    output_text.append(msg)
                else:
                    msg = 'Unexpected C-FIND query status: 0x{0:04x}'.format(status.Status)
                    output_text.append(msg)
            else:
                nsg = 'Connection timed out, was aborted or received invalid response'
                output_text.append(msg)

            results_count = results_count + 1

        # Release the association
        query_complete_time = datetime.now()
        assoc.release()
    elif assoc.is_rejected:
        msg = 'Association attempt rejected'
        output_text.append(msg)
    elif assoc.is_aborted:
        msg = 'Association attempt aborted'
        output_text.append(msg)
    else:
        msg = 'Association rejected, aborted or never connected'
        output_text.append(msg)

    # Capture timing info
    end_time = datetime.now()

    delta_t = association_complete_time - start_time
    msg = f"Time to associate: {delta_t}"
    output_text.append(msg)
    
    delta_t = query_complete_time - association_complete_time
    msg = f"Time to execute query:  {delta_t}"
    output_text.append(msg)

    delta_t = end_time-query_complete_time
    msg = f"Time to release association: {delta_t}"
    output_text.append(msg)

    #return output_text
    return response_datasets_arr

#Mwl
def mwl(request):
    a = execute_mwl_query('epicmwl.healthpartners.com')
    return HttpResponse(a, content_type = 'text/plain')
    

def cfind(request):
    return render(request, 'form.html')




