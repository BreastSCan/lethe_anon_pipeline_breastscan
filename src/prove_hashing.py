import os
from pathlib import Path
import pydicom
import base64
#from lethe.bscan_hashing import hash_dicom_uid_ready
from lethe.encryptor import IdentifierEncryptor
from lethe.bscan_hashing import hash_patient_id
from pydicom.config import settings
from pydicom import config
from pydicom.config import settings


# Hardcoded stuff
site_id = "HULAFE" 
project_id = "BREASTSCAN"
tag_mapping_hex = {
    'PatientName': {'tag': '00100010'}, 
    'PatientID': {'tag': '00100020'}, 
    'AccessionNumber': {'tag': '00080050'}, 
    'AcquisitionUID': {'tag': '00080017'},
    'StudyDescription': {'tag': '00081030'},
    'StudyInstanceUID': {'tag': '0020000D'},
    'SeriesInstanceUID': {'tag': '0020000E'},
    'FrameOfReferenceUID': {'tag': '00200052'},
    'InstanceCreatorUID': {'tag': '00080014'},
    'SOPInstanceUID': {'tag': '00080018'},
    'OverlayDate': {'tag': '00080024'},
    'CurveDate': {'tag': '00080025'},
    'RefSOPInstanceUID': {'tag': '00081155'},
    'IrradiationEventUID': {'tag': '00083010'},
    'DeviceUID': {'tag': '00181002'},
    'TargetUID': {'tag': '00182042'},
    'SourceStartDateTime': {'tag': '00189369'},
    'StartAcquisitionDateTime': {'tag': '00189516'},
    'EndAcquisitionDateTime': {'tag': '00189517'},
    'SynchronizationFrameOfReferenceUID': {'tag': '00200200'},
    'ConcatenationUID': {'tag': '00209161'},
    'DimensionOrganizationUID': {'tag': '00209164'},
    'PaletteColorLUTUID': {'tag': '00281199'},
    'LargePaletteColorLUTUID': {'tag': '00281214'},
    'SpecimenUID': {'tag': '00400554'},
    'UID': {'tag': '0040A124'},
}

"""
# tag mapping dictionary for all of the hashed dicom tags
    tag_mapping_hex = {
        'PatientName': {'tag': '00100010'}, 
        'PatientID': {'tag': '00100020'}, 
        'AccessionNumber': {'tag': '00080050'}, 
        'AcquisitionUID': {'tag': '00080017'},
        'StudyDescription': {'tag': '00081030'},
        'StudyInstanceUID': {'tag': '0020000D'},
        'SeriesInstanceUID': {'tag': '0020000E'},
        'FrameOfReferenceUID': {'tag': '00200052'},
        'InstanceCreatorUID': {'tag': '00080014'},
        'SOPInstanceUID': {'tag': '00080018'},
        'OverlayDate': {'tag': '00080024'},
        'CurveDate': {'tag': '00080025'},
        'RefSOPInstanceUID': {'tag': '00081155'},
        'IrradiationEventUID': {'tag': '00083010'},
        'DeviceUID': {'tag': '00181002'},
        'TargetUID': {'tag': '00182042'},
        'SourceStartDateTime': {'tag': '00189369'},
        'StartAcquisitionDateTime': {'tag': '00189516'},
        'EndAcquisitionDateTime': {'tag': '00189517'},
        'SynchronizationFrameOfReferenceUID': {'tag': '00200200'},
        'ConcatenationUID': {'tag': '00209161'},
        'DimensionOrganizationUID': {'tag': '00209164'},
        'PaletteColorLUTUID': {'tag': '00281199'},
        'LargePaletteColorLUTUID': {'tag': '00281214'},
        'SpecimenUID': {'tag': '00400554'},
        'UID': {'tag': '0040A124'},
    }
"""

tag_mapping_test = {
    'PatientID': {'tag': '00100020'}, 
    'AcquisitionUID': {'tag': '00080017'},
    'StudyDescription': {'tag': '00081030'},
    'StudyInstanceUID': {'tag': '0020000D'},
}
real_tag_mapping= {
    'PatientID': {'tag': '00100020'}
}
# Required variables
file_path = Path("/input/Breast_cancer_1730/MAMMOGRAFITEKMEMESAG_20220225/RMLO7130000020220225172744/1.2.840.113681.174653723.1645789096.2708.105499.dcm")
target_path = Path("/output/hashing_example.dcm")
encryptor = IdentifierEncryptor(site_id, project_id)
#print(f"Encryptor key: {encryptor.key} of length {len(encryptor.key)}")

ds = pydicom.dcmread(file_path)
for name, info in real_tag_mapping.items():
    tag_int = int(info['tag'], 16)
    
    if tag_int in ds:
        original_value = str(ds[tag_int].value)
        print(f"Original PatienID before hashing: {original_value}")

hash_patient_id(file_path, target_path, encryptor, real_tag_mapping)

encryptor2 = IdentifierEncryptor(site_id, project_id)
try:
    ds = pydicom.dcmread(target_path)
    
    for name, info in real_tag_mapping.items():
        tag_int = int(info['tag'], 16)
        
        if tag_int in ds:
            encrypted_value = str(ds[tag_int].value)
            if not encrypted_value:
                continue
            print(f"Hashed PatientID (hex): {encrypted_value}")

            #print(f"Tag name: {name}, original value: {original_value}, length {len(original_value)}")

            #if len(original_value)>32:
            #    original_value = original_value[:32]
            # 1. Get raw encrypted bytes from the engine
            # Note: Assuming IdentifierEncryptor.encrypt now returns bytes 
            # or you use a helper that does.
            try:
                decrypted_bytes = encryptor2.decrypt(bytes.fromhex(encrypted_value))
            except Exception as e:
                print(f"Encryption failed for file {target_path} tag {name} with value length {len(encrypted_value)}: {e}")
                raise

            decrypted_str = decrypted_bytes
            print(f"The value after decoding is: {decrypted_str}")

except Exception as e:
    print(f"Error processing {target_path.name}: {e}")

hash_lists = ["32_character_examplePatientIDPat","32_character_examplePatientIDPa","16_character_exa","15_character_ex"]
for hash in hash_lists:
    encryptor = IdentifierEncryptor(site_id, project_id)

    original_value = hash
    try:
        encrypted_bytes = encryptor.encrypt(original_value)
    except Exception as e:
        print(f"Encryption failed for example {hash} with value length {len(original_value)}: {e}")
        continue


    #big_int = int.from_bytes(encrypted_bytes, byteorder='big')
    #hashed_value = f"2.25.{big_int}"
    hashed_value = encrypted_bytes.hex()
    print(f"Value {hash} of length {len(hash)} hashed to {hashed_value} of length {len(hashed_value)}")




"""
    tag_mapping = {
        'PatientName': {'tag': (16, 16), 'is_identifier': False}, 
        'PatientID': {'tag': (16, 32), 'is_identifier': True}, 
        'StudyDate': {'tag': (8, 32), 'is_identifier': False}, 
        'Modality': {'tag': (8, 96), 'is_identifier': False}, 
        'AccessionNumber': {'tag': (8, 80), 'is_identifier': False}, 
        'StudyDescription': {'tag': (8, 4144), 'is_identifier': False}, 
        'StudyUID': {'tag': (32, 13), 'is_identifier': True}, 
        'StudyTime': {'tag': (8, 48), 'is_identifier': False},
        'SerieUID': {'tag': (32, 14), 'is_identifier': False}
    }
    tag_mapping = {
        'PatientName': {'tag': (16, 16)}, 
        'PatientID': {'tag': (16, 32)}, 
        'AccessionNumber': {'tag': (8, 80)}, 
        'AcquisitionUID': {'tag': (8, 23)},
        'StudyDescription': {'tag': (8, 4144)},
        'StudyInstanceUID': {'tag': (32, 13)},
        'SeriesInstanceUID': {'tag': (32, 14),},
        'FrameOfReferenceUID': {'tag': (32, 82),},
    }    
"""