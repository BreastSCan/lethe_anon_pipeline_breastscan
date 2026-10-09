from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from hashlib import sha256

class IdentifierEncryptor:
    def __init__(self, site_id: str, project_id: str):
        """
        Deterministically derive 32-byte key and 16-byte IV
        AES-CBC will use a combined key and an Init Vec -IV.
        """

        # 1. Derive the AES-256 Key (32 bytes)
        # We combine Site and Project IDs to ensure the key is unique to both.
        combined_key_seed = f"{site_id}{project_id}".encode()
        self.key = sha256(combined_key_seed).digest()

        # 2. Derive the IV (16 bytes)
        # We use the Project ID alone so that the 'starting point' 
        # is consistent for all files within the same project.
        iv_seed = project_id.encode()
        self.iv = sha256(iv_seed).digest()[:16]

        self.backend = default_backend()

    def encrypt(self, identifier: str) -> bytes:
        # 1. Ensure input is within bounds
        #if not (8 <= len(identifier) <= 32):
        #    raise ValueError("Ids must be between 8 and 32 char.")
        if not (len(identifier) <= 32):
            raise ValueError("Ids must have 32 characters or less.")


       # 2. Setup Padder (Ensures output is exactly 32 bytes)
        # To force exactly 32 bytes output for a 32-byte input, 
        # we must handle the block size strictly.
        padder = padding.PKCS7(128).padder()
        padded_data = ( padder.update(identifier.encode()) 
                      + padder.finalize()
        )

        # 3. Encrypt
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), 
                 backend=self.backend
        )
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()
    #   return encrypted_bytes.hex()[:64]

    def decrypt(self, encrypted_data: bytes) -> str:
        # 1. Decrypt
        cipher = Cipher(algorithms.AES(self.key), 
                 modes.CBC(self.iv), 
                 backend=self.backend
        )
        decryptor = cipher.decryptor()
        padded_data = ( decryptor.update(encrypted_data)
                      + decryptor.finalize()
        )

        # 2. Unpad
        unpader = padding.PKCS7(128).unpadder()
        data = unpader.update(padded_data) + unpader.finalize()
        return data.decode()
