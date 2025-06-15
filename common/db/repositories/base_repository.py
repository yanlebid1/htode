# common/db/repositories/base_repository.py

from sqlalchemy.orm import Session
from typing import TypeVar, Generic, Type, Optional, List

from common.utils.logging_config import log_operation, log_context

# Import the repository logger
from . import logger

T = TypeVar('T')


class BaseRepository(Generic[T]):
    @staticmethod
    @log_operation("get_by_id")
    def get_by_id(db: Session, model_class: Type[T], id: int) -> Optional[T]:
        """Get entity by ID"""
        with log_context(logger, model=model_class.__name__, id=id):
            entity = db.query(model_class).filter(model_class.id == id).first()
            if entity:
                logger.debug("Found entity", extra={
                    'model': model_class.__name__,
                    'id': id
                })
            else:
                logger.debug("Entity not found", extra={
                    'model': model_class.__name__,
                    'id': id
                })
            return entity

    @staticmethod
    @log_operation("get_all")
    def get_all(db: Session, model_class: Type[T]) -> List[T]:
        """Get all entities"""
        with log_context(logger, model=model_class.__name__):
            entities = db.query(model_class).all()
            logger.debug("Retrieved all entities", extra={
                'model': model_class.__name__,
                'count': len(entities)
            })
            return entities

    @staticmethod
    @log_operation("create")
    def create(db: Session, model_class: Type[T], data: dict) -> T:
        """Create a new entity"""
        with log_context(logger, model=model_class.__name__):
            entity = model_class(**data)
            db.add(entity)
            db.commit()
            db.refresh(entity)
            logger.info("Created entity", extra={
                'model': model_class.__name__,
                'id': getattr(entity, 'id', None)
            })
            return entity

    @staticmethod
    @log_operation("update")
    def update(db: Session, entity: T, data: dict) -> T:
        """Update an existing entity"""
        with log_context(logger, model=entity.__class__.__name__, id=getattr(entity, 'id', None)):
            for key, value in data.items():
                setattr(entity, key, value)
            db.commit()
            db.refresh(entity)
            logger.info("Updated entity", extra={
                'model': entity.__class__.__name__,
                'id': getattr(entity, 'id', None),
                'updated_fields': list(data.keys())
            })
            return entity

    @staticmethod
    @log_operation("delete")
    def delete(db: Session, entity: T) -> bool:
        """Delete an entity"""
        with log_context(logger, model=entity.__class__.__name__, id=getattr(entity, 'id', None)):
            db.delete(entity)
            db.commit()
            logger.info("Deleted entity", extra={
                'model': entity.__class__.__name__,
                'id': getattr(entity, 'id', None)
            })
            return True