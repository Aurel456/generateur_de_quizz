const FrHeaderConfig = {
    operator: {
        image: { show: false, src: '', altText: 'Logo', orientation: 'vertical', width: '0rem' },
        enlargeLink: true,
        organisation: 'Générateur de Quiz & Exercices IA',
        link: 'HomePage',
        isBeta: true,
        appTitle: import.meta.env.VITE_APP_TITLE,
        linkTitle: '',
    },
    headerTools: [],
    searcher: { show: false },
    display: { show: true, index: 0 },
    translate: { show: false },
};

export default FrHeaderConfig;
