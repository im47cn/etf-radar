import { useContext } from 'react';
import { EventsContext } from '@/providers/eventsContext';

export const useUserEvents = () => useContext(EventsContext);
