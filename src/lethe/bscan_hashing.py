from queue import Queue
from threading import Thread
import pydicom
import os
from pathlib import Path
from tqdm import tqdm
from .encryptor import IdentifierEncryptor
from loguru import logger

def hash_dicom(
    dicom_file: Path, 
    output_file: Path, 
    encryptor: IdentifierEncryptor, 
    tag_mapping: dict
):
    try:
        ds = pydicom.dcmread(dicom_file)
        
        for name, info in tag_mapping.items():
            tag_hex = info['tag']
            # Convert '00100010' string to a pydicom Tag object or hex integer
            tag_int = int(tag_hex, 16)
            
            if tag_int in ds:
                original_value = str(ds[tag_int].value)
                # Encrypt and update the specific tag
                ds[tag_int].value = encryptor.encrypt(original_value)
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(output_file)
    except Exception as e:
        print(f"Error processing {dicom_file}: {e}")

def hash_patient_id(
    dicom_file: Path, 
    output_file: Path, 
    encryptor: IdentifierEncryptor
):
    try:
        ds = pydicom.dcmread(dicom_file)
        
        patient_id_tag = int("00100020", 16)
        patient_name_tag = int('00100010', 16)

        # Always encrypt PatientID, even if empty
        if patient_id_tag not in ds:
            raise KeyError(f"PatientID tag not found in {dicom_file}")
        
        original_patient_id = str(ds[patient_id_tag].value)
        try:
            encrypted_bytes = encryptor.encrypt(original_patient_id)
        except Exception as e:
            print(f"Encryption failed for file {dicom_file} tag PatientID with value length {len(original_patient_id)}: {e}")
            raise

        hashed_patient_id = encrypted_bytes.hex()
        ds[patient_id_tag].value = hashed_patient_id

        # Always set PatientName to "<hashed_patient_id> , Anonymous"
        if patient_name_tag not in ds:
            raise KeyError(f"PatientName tag not found in {dicom_file}")

        ds[patient_name_tag].value = f"BREASTCAN-{hashed_patient_id}, Anonymous"
        
        # Save the modified file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(output_file)

    except Exception as e:
        print(f"Error processing {dicom_file.name}: {e}")
        raise

# Multithreading code to hash files at the same time
def producer(
    input_dir: Path, 
    task_queue: Queue, 
    num_consumers: int
):
    """Finds all DICOM files and adds them to the queue."""
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(".dcm"):
                task_queue.put(Path(root) / file)
    
    # Signal consumers to stop
    for _ in range(num_consumers):
        task_queue.put(None)

def consumer(
    task_queue: Queue, 
    input_dir: Path, 
    output_dir: Path, 
    encryptor: IdentifierEncryptor
):
    """Processes files from the queue."""
    while True:
        file_path = task_queue.get()
        if file_path is None:
            task_queue.task_done()
            break
        
        # Maintain directory structure: Patient/Study/Series/file.dcm
        rel_path = file_path.relative_to(input_dir)
        target_path = output_dir / rel_path
        
        hash_patient_id(file_path, target_path, encryptor)
        task_queue.task_done()

# This function runs the hashing of the files in a multithreaded manner by paralellizing at the dicom file level
def hash_BS_id(
    input_dir: Path, # folder containing all the data
    output_dir: Path,
    site_id: str,
    project_id:str,
    threads: int,
):
    # One thread finds all the dicom files (the producer) and distributes them to the rest of the threads (the consumers) for hashing 
    task_queue = Queue(maxsize=5000)
    encryptor = IdentifierEncryptor(site_id, project_id)
    
    num_consumers = max(1, threads - 1)
    # Launch Workers
    workers = []
    for _ in range(num_consumers):
        t = Thread(target=consumer, args=(task_queue, input_dir, output_dir, encryptor))
        t.daemon = True
        t.start()
        workers.append(t)

    # Launch Producer
    producer_thread = Thread(target=producer, args=(input_dir, task_queue, num_consumers))
    producer_thread.start()

    producer_thread.join()
    for t in workers:
        t.join()

    #print(f"Successfully hashed DICOM files with the BreastScan hashing scheme.")