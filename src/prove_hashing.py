import os
from pathlib import Path
import pydicom
import base64
from lethe.encryptor import IdentifierEncryptor
from lethe.bscan_hashing import hash_patient_id
from pydicom.config import settings
from pydicom import config


# Hardcoded stuff
site_id = "HULAFE" 
project_id = "BREASTSCAN"
real_tag_mapping= {
    'PatientID': {'tag': '00100020'}
}
bol_show_variable_length_examples = True

# Required variables
file_path = Path("/input/Hacer anónimoarpon2022/Hacer anónimo2022.Seq1.Ser71100000.Img1.dcm")
target_path = Path("/output/hashing_example.dcm")
encryptor = IdentifierEncryptor(site_id, project_id)
#print(f"Encryptor key: {encryptor.key} of length {len(encryptor.key)}")

print("Script to hash a patientID as an example to prove encryption and decryption using the proposed BreastSCan scheme.")
ds = pydicom.dcmread(file_path)
for name, info in real_tag_mapping.items():
    tag_int = int(info['tag'], 16)
    
    if tag_int in ds:
        original_value = str(ds[tag_int].value)
        print(f"Original PatienID before hashing: {original_value}")

hash_patient_id(file_path, target_path, encryptor, real_tag_mapping)
del encryptor

# Create a new encryptor with same site and project ids
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
            try:
                decrypted_bytes = encryptor2.decrypt(bytes.fromhex(encrypted_value))
            except Exception as e:
                print(f"Encryption failed for file {target_path} tag {name} with value length {len(encrypted_value)}: {e}")
                raise

            decrypted_str = decrypted_bytes
            print(f"The value after decoding is: {decrypted_str}")

except Exception as e:
    print(f"Error processing {target_path.name}: {e}")

if bol_show_variable_length_examples:
    # Print lengths of encrypted values.
    # Values with accents can occupy more bytes.
    hash_lists = ["32_character_examplePatientIDPat","32_character_examplePatientIDPa","16_character_exa","15_character_ex"]
    for hash in hash_lists:
        encryptor = IdentifierEncryptor(site_id, project_id)

        original_value = hash
        try:
            encrypted_bytes = encryptor.encrypt(original_value)
        except Exception as e:
            print(f"Encryption failed for example {hash} with value length {len(original_value)}: {e}")
            continue

        hashed_value = encrypted_bytes.hex()
        print(f"Value {hash} of length {len(hash)} hashed to {hashed_value} of length {len(hashed_value)}")
