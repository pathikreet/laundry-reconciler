import sys
import os
sys.path.append(os.path.abspath("."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.models import *  # ensure all models loaded
from src.importers.notepad import NotepadImporter

def test_import():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    importer = NotepadImporter(session)
    file_path = 'd:/Pathikreet/Workspace/Laundry-Reconciler/laundry-reconciler-docs/sample/Delivery_notes_October.csv'
    
    try:
        result = importer.run(file_path)
        print(f"Import successful: {result}")
    except Exception as e:
        print(f"Import failed with error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_import()
