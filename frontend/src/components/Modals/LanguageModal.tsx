import { Modal } from 'antd';

import { memo } from 'react';
import { useTranslation } from 'react-i18next';

// Constants
import { AVAILABLE_LANGUAGES } from '../../constants/languages';

// Redux
import { languageActions } from '../../store/slices/language';
import { useAppDispatch, useAppSelector } from '../../store/store';

// Interfaces
import type { Languages } from '../../interfaces/languages';

export const LanguageModal = memo(() => {
  const dispatch = useAppDispatch();
  const [t] = useTranslation(['navbar']);
  const open = useAppSelector((state) => state.language.isModalOpen);

  const onClose = (value?: Languages) => {
    dispatch(languageActions.closeLanguageModal({ language: value }));
  };

  return (
    <>
      <Modal
        centered
        width={900}
        open={open}
        footer={null}
        destroyOnHidden
        className='language-modal'
        onCancel={() => onClose()}
        title={
          <h1
            style={{
              fontWeight: 700,
              fontSize: '1.5rem',
              marginBlockStart: 0,
              paddingBlockEnd: 8,
              color: 'white',
            }}
          >
            {t('Choose a language')}
          </h1>
        }
      >
        <div className='language-grid'>
          {AVAILABLE_LANGUAGES.map((language) => (
            <button key={language.value} onClick={() => onClose(language.value)}>
              <span className='title'>{language.label}</span>
              <span className='subtitle'>{language.englishLabel}</span>
            </button>
          ))}
        </div>
      </Modal>
    </>
  );
});

LanguageModal.displayName = 'LanguageModal';
