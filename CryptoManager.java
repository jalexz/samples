/****************************************************************************
 * This is a snippet from an old project I made for my Distributed Systems  *
 * course back in 2008 when I was a student at Politecnico di Milano.		*
 * It is a module that implements Diffie-Hellmann key exchange protocol for * 
 * a group chat.															*
 * I'm sorry for the Italian still in the comments, I'll translate them as  *
 * soon as I can.														    *
 ****************************************************************************/
 
package it.polimi.distsys0708.demo.gdh.groupmember;

import it.polimi.distsys0708.demo.gdh.utils.GDHParams;
import it.polimi.distsys0708.demo.gdh.utils.IntermediateValue;
import it.polimi.distsys0708.demo.gdh.utils.KAMValues;

import java.math.BigInteger;
import java.security.InvalidAlgorithmParameterException;
import java.security.InvalidKeyException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashSet;
import java.util.Set;
import java.util.logging.Logger;

import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyAgreement;
import javax.crypto.NoSuchPaddingException;
import javax.crypto.SecretKey;
import javax.crypto.spec.DHParameterSpec;

/**
 * Gestisce la crittografia ed il key agreement all'interno di un {@link GroupMemberImpl}.
 * Le operazioni svolte da questa classe sono:
 * <ul>
 *   <li> Inizializzazione del key agreement con i parametri GDH del gruppo corrente, 
 *        attraverso il metodo {@link #init(GDHParams)};
 *   <li> Esecuzione del protocollo di key agreement attraverso i metodi 
 *        {@link #doUpflow(KAMValues, BigInteger, boolean)}, 
 *        {@link #doDownflow(KAMValues, BigInteger)};
 *   <li> Crittografia dei messaggi in ingresso/uscita attraverso i metodi
 *        {@link #decryptMessage(byte[])} e {@link #encryptMessage(String)}.
 * </ul>
 * Nota: nella documentazione della classe si fara' riferimento agli oggetti KAMValues
 * come se fossero dei messaggi di key agreement, anche se in realta' ne costituiscono
 * solo una parte (la piu' importante).
 */
public class CryptoManager {
	
	/* Generatore di coppie di chiavi pubblica/privata. */
	private final KeyPairGenerator key_pair_generator;
	
	/* Esecutore del protocollo di key agreement. */
    private final KeyAgreement key_agreement;
    
    /* Cifrario di input (crittografazione messaggi). */
    private Cipher input_cipher;
    
    /* Cifrario di output (decrittazione messaggi). */
    private Cipher output_cipher;
    
    /* Parametri del protocollo GDH.2 da utilizzare per la crittografia. */
    private GDHParams gdh_params;
    
    /* Coppia di chiavi pubblica/privata usata per la crittografia. */
    private KeyPair key_pair;
    
    /* Ultimo messaggio di upflow ricevuto. */
    private KAMValues last_upflow_recvd;
	
    /* Logger della classe. */
    private final Logger logger;
    
	/**
	 * Costruttore della classe.
	 * Ottiene un generatore di coppie di chiavi ed un esecutore del protocollo di
	 * key agreement per l'algoritmo di Diffie-Hellman.
	 * 
	 * @throws NoSuchAlgorithmException se si verifica un errore durante l'ottenimento
	 *         del generatore di coppie di chiavi e dell'esecutore del key agreement.
	 */
	public CryptoManager() throws NoSuchAlgorithmException {
		
		/* Ottiene il logger della classe. */
		logger = Logger.getLogger(this.getClass().getName());
		logger.finest("Logger della classe " + this.getClass().getName() + " pronto.");
		
		/* Ottiene un generatore di coppie di chiavi per l'algoritmo Diffie-Hellman. */
		key_pair_generator = KeyPairGenerator.getInstance("DH");
		logger.finest("Ottenuto il generatore di coppie di chiavi per Diffie-Hellman.");
		
		/* Ottiene una implementazione del protocollo di key agreement per l'algoritmo 
		 * Diffie-Hellman. */
		key_agreement = KeyAgreement.getInstance("DH");
		logger.finest("Ottenuto l'esecutore del protocollo di key agreement per Diffie-Hellman.");
		
		/* Questi campi vengono inizializzati successivamente con il metodo init(). */
		input_cipher = null;
		output_cipher = null;
		gdh_params = null;
		key_pair= null;
		last_upflow_recvd = null;
		
	}
	
	/**
	 * Inizializza gli elementi crittografici dipendenti dai parametri GDH del gruppo di
	 * appartenenza. Un oggetto {@link CryptoManager} deve essere reinizializzato con
	 * questo metodo tutte le volte che i parametri GDH.2 del gruppo di appartenenza
	 * cambiano.
	 * @param gdhp parametri del protocollo GDH.2 con cui inizializzare la crittografia.
	 * @throws NoSuchAlgorithmException se si verifica un errore durante 
	           l'inizializzazione degli elementi crittografici.
	 * @throws NoSuchPaddingException se si verifica un errore durante 
	           l'inizializzazione degli elementi crittografici.
	 * @throws InvalidAlgorithmParameterException se si verifica un errore durante 
	           l'inizializzazione degli elementi crittografici.
	 * @throws InvalidKeyException se si verifica un errore durante 
	           l'inizializzazione degli elementi crittografici.
	 */
	public synchronized void init(GDHParams gdhp) throws NoSuchAlgorithmException, NoSuchPaddingException, InvalidAlgorithmParameterException, InvalidKeyException {
		
		gdh_params = gdhp;
		logger.finest("Inizializzazione della crittografia con i seguenti parametri:\n" +
				gdhp);
		
		/* Ottiene i cifrari di input e output associati all'agoritmo di
		 * cifratura simmetrica specificato nei parametri del GHD.2. */
		input_cipher = Cipher.getInstance(gdhp.encryption_algorithm);
		logger.finest("Ottenuto il cifrario di input.");
	    output_cipher = Cipher.getInstance(gdhp.encryption_algorithm);
	    logger.finest("Ottenuto il cifrario di output.");
		
	    /* Inizializza il generatore di coppie di chiavi con i parametri
		 * del GDH.2. */
	    key_pair_generator.initialize(
				new DHParameterSpec( gdh_params.p, gdh_params.g, gdh_params.l )
		);
		logger.finest("Generatore di coppie di chiavi pubblica/privata inizializzato.");
	    
	    /* Genera la coppia di chiavi pubblica/privata. */
		key_pair = key_pair_generator.generateKeyPair();
		logger.finest("Coppia di chiavi pubblica/privata generata.");
		
		/* Inizializza l'esecutore del key agreement con la chiave privata
		 * appena generata. */
		key_agreement.init(key_pair.getPrivate());
		logger.finest("Esecutore del key agreement inizializzato con la chiave privata.");
		
		/* Dopo ogni inizializzazione, l'ultimo messaggio di upflow ricevuto viene 
		 * cancellato. */
		last_upflow_recvd = null;
		
	}
	
	/**
	 * Cifra un messaggio usando la chiave simmetrica corrente.
	 * @param il messaggio in chiaro da cifrare.
	 * @return un array di byte contenente il messaggio cifrato.
	 * @throws IllegalBlockSizeException se si verifica un errore durante la cifratura
	 *         del messaggio.
	 * @throws BadPaddingException se si verifica un errore durante la cifratura
	 *         del messaggio.
	 * @throws IllegalStateException se il cifrario di output non e' stato inizializzato
	 *         con una chiave simmetrica o non e' stato ancora creato.
	 */
	public synchronized byte[] encryptMessage(String plain_msg) throws IllegalBlockSizeException, BadPaddingException, IllegalStateException {
		
		if (output_cipher == null)
			throw new IllegalStateException("Il cifrario di output non e' stato ancora creato.");
		
		return output_cipher.doFinal(plain_msg.getBytes());
		
	}
	
	/**
	 * Decifra un messaggio cifrato usando la chiave simmetrica corrente.
	 * @param encrypted_msg messaggio cifrato da decifrare.
	 * @return il messaggio in chiaro.
	 * @throws IllegalBlockSizeException se si verifica un errore durante la decifratura
	 *         del messaggio.
	 * @throws BadPaddingException se si verifica un errore durante la decifratura
	 *         del messaggio.
	 * @throws IllegalStateException se il cifrario di inpput non e' stato inizializzato
	 *         con una chiave simmetrica o non e' stato ancora creato.
	 */
	public synchronized String decryptMessage(byte[] encrypted_msg) throws IllegalBlockSizeException, BadPaddingException, IllegalStateException {
		
		if (input_cipher == null)
			throw new IllegalStateException("Il cifrario di input non e' stato ancora creato.");
		
		return new String(input_cipher.doFinal(encrypted_msg));
		
	}
	
	/**
	 * Effettua un passo della fase di upflow dell'algoritmo di key agreement GHD.2.
	 * Il passo puo' essere effettuato come:
	 *  <ul>
	 *    <li> membro iniziale: viene creato un messaggio di key agreement iniziale, 
	 *         da passare al membro successivo.
	 *    <li> membro intermedio: viene creato un messaggio di key agreement intermedio, 
	 *         a partire dal messaggio precedente. Il nuovo messaggio verra' passato al 
	 *         membro successivo.
	 *    <li> membro finale: viene ricavata la chiave di gruppo e viene generato (a 
	 *         partire dal messaggio precedente) un messaggio di key agreement finale da 
	 *         inviare in broadcast agli altri membri del gruppo affinche' anch'essi 
	 *         possano ricavare (in maniera sicura) la medesima chiave di gruppo.
	 * @param kam messaggio di key agreement precedente. Se <code>null</code>, viene 
	 *        eseguito il passo iniziale di upflow.
	 * @param member_id identificativo del membro del gruppo che sta effettuando il passo 
	 *        corrente di upflow.
	 * @param last vale <code>true</code> se deve essere effettuato il passo finale di 
	 *        upflow.
	 * @return il messaggio di key agreement per il passo successivo.
	 * @throws InvalidKeyException se si verifica un errore durante la fase di upflow.
	 * @throws IllegalStateException se si effettua la fase di upflow in uno stato erroneo
	 *         (ad es. prima di aver generato una coppia di chiavi pubblica/privata).
	 * @throws NoSuchAlgorithmException se si verifica un errore durante la fase di upflow.
	 * @throws NullPointerException se <code>member_id</code> e' <code>null</code>.
	 * @throws IllegalArgumentException se il contenuto di <code>kam</code> non e' adatto
	 *         ad eseguire la fase di upflow richiesta.
	 */
	public synchronized KAMValues doUpflow(KAMValues kam, BigInteger member_id, boolean last) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException, IllegalArgumentException {
		
		if (member_id == null)
			throw new NullPointerException("Specificato un id membro non valido: null.");
		
		if (kam == null && last)
			throw new IllegalArgumentException("I parametri 'kam' e 'last' hanno valori " +
					"incompatibili: kam = null e last = true. Il passo di upflow non" +
					"puo' essere contemporaneament iniziale e finale.");
		
		/* Salva l'ultimo messaggio di upflow ricevuto. */
		last_upflow_recvd = (kam != null ? kam.clone() : null);
		
		/* Il nuovo messaggio di key agreement. */
		KAMValues result = null;
		
		if (!last) {
			if (kam == null) {
				/* Inizia la fase di upflow. */
				result = startUpflow(member_id);
			}
			else {
				/* Continua la fase di upflow. */
				result = continueUpflow(kam, member_id);
			}
		}
		else {
			/* Termina la fase di upflow. */
			if (kam.cardinal_value == null)
				throw new IllegalArgumentException("Specificato un key agreement message non valido: il valore cardinale e' null.");
			result = endUpflow(kam, member_id);
		}
		
		return result;
	}

	/**
	 * Rieffettua un passo della fase di upflow dell'algoritmo di key agreement GHD.2.
	 * Come operazione preliminare, viene generata una nuova coppia di chiavi
	 * pubblica/privata da usare nel protocollo di key agreement. Se necessario,
	 * vengono eseguite le opportune azioni per escludere dal key agreement i membri
	 * specificati.
	 * Il passo puo' essere effettuato come:
	 *  <ul>
	 *    <li> membro intermedio: viene creato un messaggio di key agreement intermedio,
	 *         a partire dall'ultimo messaggio di upflow ricevuto.
	 *    <li> membro finale: viene ricavata la chiave di gruppo e viene generato (a 
	 *         partire dall'ultimo messaggio di upflow ricevuto) un messaggio di key 
	 *         agreement finale da inviare in broadcast agli altri membri del gruppo 
	 *         affinche' anch'essi possano ricavare (in maniera sicura) la medesima 
	 *         chiave di gruppo.
	 *  </ul>
	 * @param member_id identificativo del membro del gruppo che sta effettuando il passo 
	 *        corrente di upflow.
	 * @param last vale <code>true</code> se deve essere effettuato il passo finale di 
	 *        upflow.
	 * @param excluded_members un insieme di identificatori di membri del gruppo che
	 *        devono essere esclusi dalle successive fasi di key agreement. Puo' essere 
	 *        <code>null</code>.
	 * @return il messaggio di key agreement per il passo successivo.
	 * @throws InvalidKeyException se si verifica un errore durante la fase di upflow.
	 * @throws NoSuchAlgorithmException se si verifica un errore durante la fase di upflow.
	 * @throws IllegalStateException se si effettua la fase di upflow in uno stato erroneo.
	 * @throws NullPointerException se <code>member_id</code> e' <code>null</code>.
	 */
	public synchronized KAMValues redoUpflow(BigInteger member_id, boolean last, Set<BigInteger> excluded_members) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException {
		
		if (member_id == null)
			throw new NullPointerException("Specificato un id membro non valido: null.");
		
		/* Se non e' stato memorizzato nessun messaggio di upflow lancia un'eccezione. */
		if (last_upflow_recvd == null) {
			throw new IllegalStateException("Impossibile rieseguire l'upflow: nessun messaggio di upflow e' stato precedentemente ricevuto.");
		}
		
		/* Esclude eventuali membri del gruppo dalle successive fasi di key agreement. */
		if (excluded_members != null) {
			logger.fine("Saranno esclusi dal key agreement i seguenti membri: " + excluded_members);
			Deque<IntermediateValue> d_tmp = 
				new ArrayDeque<IntermediateValue>(last_upflow_recvd.intermediate_values);
			last_upflow_recvd.excludeMembers(excluded_members);
			d_tmp.removeAll(last_upflow_recvd.intermediate_values);
			logger.finer("Sono stati rimossi i seguenti valori intermedi: " + d_tmp);
		}
		
		logger.finest("Ultimo messaggio di upflow ricevuto: " + last_upflow_recvd);
		
		/* Genera una nuova coppia di chiavi pubblica/privata prima
		 * di eseguire il passo di upflow. */
		key_pair = key_pair_generator.generateKeyPair();
		logger.finest("Coppia di chiavi pubblica/privata generata.");

		/* Inizializza l'esecutore del key agreement con la chiave privata
		 * appena generata. */
		key_agreement.init(key_pair.getPrivate());
		logger.finest("Esecutore del key agreement inizializzato con la chiave privata.");
			
		/* Il nuovo messaggio di key agreement. */
		KAMValues result = null;
		
		if (!last) {
			/* Continua la fase di upflow. */
			result = continueUpflow(last_upflow_recvd.clone(), member_id);
		}
		else {
			/* Termina la fase di upflow. */
			if (last_upflow_recvd.cardinal_value == null)
				throw new IllegalStateException("Impossibile effettuare la fase finale " +
						"di upflow: l'ultimo valore di upflow memorizzato ha un valore " +
						"cardinale pari a null.");
			result = endUpflow(last_upflow_recvd.clone(), member_id);
		}
		
		return result;
		
	}
	
	/**
	 * Effettua la fase di downflow dell'algoritmo di key agreement GDH.2.
	 * Questa fase consiste semplicemente nell'ottenere la chiave simmetrica di gruppo
	 * a partire dal valore cardinale contenuto nel messaggio di key agreement ricevuto.
	 * @param kam messaggio di key agreement ricevuto.
	 * @throws InvalidKeyException se si verifica un errore durante il calcolo della
	 *         chiave simmetrica.
	 * @throws IllegalStateException se si effettua la fase di downflow in uno stato 
	 *         erroneo.
	 * @throws NoSuchAlgorithmException se si verifica un errore durante il calcolo della
	 *         chiave simmetrica.
	 * @throws NullPointerException se <code>kam</code> e' <code>null</code>.
	 * @throws IllegalArgumentException se il contenuto di <code>kam</code> non e' adatto
	 *         ad eseguire la fase di downflow.
	 * 
	 */
	public synchronized void doDownflow(KAMValues kam) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException, IllegalArgumentException {
		
		if (kam == null)
			throw new NullPointerException("Specificato un key agreement message non valido: null.");
		else if(kam.cardinal_value == null)
			throw new IllegalArgumentException("Specificato un key agreement message non valido: il valore cardinale e' null.");
		
		/* Calcola la nuova chiave simmetrica di gruppo utilizzando il precedente 
		 * valore cardinale. */
		computeSecretKey(kam.cardinal_value.value);
		
	}
		
	/**
	 * Effettua la fase di upflow da membro finale:
	 * calcola il nuovo insieme di valori intermedi elevando alla chiave privata tutti
	 * i precedenti valori intermedi, quindi calcola la chiave simmetrica di gruppo usando
	 * il precedente valore cardinale. I cifrari di I/O vengono inizializzati per l'utilizzo
	 * della nuova chiave.
	 * @param kam messaggio di key agreement precedente. Se null, viene eseguito il passo
	 *        iniziale di upflow.
	 * @param member_id identificativo del membro del gruppo che sta effettuando il passo 
	 *        corrente di upflow.
	 * @return il messaggio di key agreement da usare al passo successivo.
	 * @throws InvalidKeyException se si verifica un errore durante l'esecuzione
	 *         della fase di upflow.
	 * @throws IllegalStateException se la fase di upflow e' fatta con uno stato erroneo
	 *         degli elementi crittografci interessati (ad es. non e' stata generata nessuna
	 *         coppia di chiavi pubblica/privata).
	 * @throws NoSuchAlgorithmException se si verifica un errore durante l'esecuzione
	 *         della fase di upflow.
	 */
	private KAMValues endUpflow(KAMValues kam, BigInteger member_id) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
		
		KAMValues result; 
		IntermediateValue iv_tmp;
		Key k_tmp;
		Set<BigInteger> s_tmp;
		
		/* Il nuovo insieme di valori intermedi avra' al piu' un elemento in piu' rispetto
		 * al vecchio insieme. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(kam.intermediate_values.size()+1);

		if (kam.intermediate_values.size() == 0) {
			/* Se il vecchio insieme dei valori intermedi e' vuoto, inserisce la propria
			 * chiave pubblica come nuovo valore intermedio. */
			k_tmp = key_pair.getPublic();
			s_tmp = new HashSet<BigInteger>();
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp, k_tmp);
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		for (int i = 0; kam.intermediate_values.size() > 0; i++) {
			/* Estrae un valore intermedio. */
			iv_tmp = kam.intermediate_values.removeFirst();
			logger.finer("Estratto il vecchio valore intermedio " + iv_tmp);
			/* Calcola il nuovo valore intermedio. */
			k_tmp = key_agreement.doPhase(iv_tmp.value, false);
			s_tmp = new HashSet<BigInteger>(iv_tmp.members);
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp,k_tmp);
			/* Aggiunge il nuovo valore intermedio al nuovo insieme. */
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}

		/* Crea il nuovo messaggio di key agreement (non e' previsto un valore
		 * cardinale). */
		result = new KAMValues(new_int_val, null);
		
		/* Calcola la nuova chiave simmetrica di gruppo utilizzando il precedente 
		 * valore cardinale. */
		computeSecretKey(kam.cardinal_value.value);
		
		return result; 
		
	}

	/**
	 * Calcola la nuova chiave simmetrica da usare nella comunicazione con gli altri membri
	 * del gruppo. I cifrari di I/O vengono inizializzati con questa nuova chiave.
	 * @param card_val valore cardinale da usare per il calcolo della chiave.
	 * @throws InvalidKeyException
	 * @throws IllegalStateException
	 * @throws NoSuchAlgorithmException
	 */
	private void computeSecretKey(Key card_val) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException {
		
		/* Calcola il segreto di sessione elevando il precedente valore cardinale
		 * alla chiave privata. */
		key_agreement.doPhase(card_val, true);
		logger.finest("Calcolato il segreto di sessione.");
		
		/* Calcola la chiave simmetrica che sara' usata per la comunicazione sicura
		 * con gli altri membri del gruppo. */
		SecretKey secret_key = key_agreement.generateSecret(gdh_params.encryption_algorithm);
		logger.fine("Calcolata la nuova chiave simmetrica di gruppo: " + 
				Integer.toHexString(secret_key.hashCode())+ " (" + 
				(secret_key.getEncoded().length*8) + "bit)");
		
		/* Inizializza i cifrari di input/output con la nuova chiave simmetrica. */
		input_cipher.init(Cipher.DECRYPT_MODE, secret_key);
		logger.finest("Cifrario di input inizializzato con la chiave simmetrica.");
		output_cipher.init(Cipher.ENCRYPT_MODE, secret_key);
		logger.finest("Cifrario di output inizializzato con la chiave simmetrica.");
		
	}

	/**
	 * Effettua la fase di upflow da membro intermedio:
	 * calcola il nuovo insieme di valori intermedi elevando alla chiave privata tutti
	 * i precedenti valori intermedi ed aggiungendo il precedente valore cardinale, quindi
	 * calcola il nuovo valore cardinale elevando il precedente alla chiave privata.
	 * @param kam il messaggio contenente i vecchi valori intermedi ed il vecchio
	 *        valore cardinale.
	 * @param member_id identificativo del membro del gruppo che sta eseguendo il passo
	 *        corrente della fase di upflow.
	 * @return un nuovo messaggio di key agreement con i nuovi valori intermedi e nuovo
	 *         valore cardinale.
	 * @throws InvalidKeyException se si verifica un errore durante l'esecuzione
	 *         della fase di upflow.
	 * @throws IllegalStateException se si esegue la fase di upflow con uno stato erroneo
	 *         degli elementi crittografci interessati (ad es. non e' stata generata nessuna
	 *         coppia di chiavi pubblica/privata).
	 */
	private KAMValues continueUpflow(KAMValues kam, BigInteger member_id) throws InvalidKeyException, IllegalStateException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
		
		IntermediateValue iv_tmp;
		Key k_tmp;
		HashSet<BigInteger> s_tmp;
		
		/* Il nuovo insieme di valori intermedi avra' al piu' due elementi in piu' 
		 * rispetto al vecchio insieme. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(kam.intermediate_values.size()+2);

		/* Il vecchio valore cardinale diventa uno dei nuovi valori intermedi. */
		new_int_val.addLast(kam.cardinal_value.clone());
		logger.finer("Aggiunto il nuovo valore intermedio " + kam.cardinal_value);

		if (kam.intermediate_values.size() == 0) {
			/* Se il vecchio insieme dei valori intermedi e' vuoto, inserisce la propria
			 * chiave pubblica come nuovo valore intermedio. */
			k_tmp = key_pair.getPublic();
			s_tmp = new HashSet<BigInteger>();
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp, k_tmp);
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		for (int i = 0; kam.intermediate_values.size() > 0; i++) {
			/* Estrae un valore intermedio. */
			iv_tmp = kam.intermediate_values.removeFirst();
			logger.finer("Estratto il vecchio valore intermedio " + iv_tmp);
			/* Calcola il nuovo valore intermedio. */
			k_tmp = key_agreement.doPhase(iv_tmp.value, false);
			s_tmp = new HashSet<BigInteger>(iv_tmp.members);
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp,k_tmp);
			/* Aggiunge il nuovo valore intermedio al nuovo insieme. */
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		
		/* Calcola il nuovo valore cardinale: e' il vecchio elevato alla chiave
		 * privata corrente. */
		k_tmp = key_agreement.doPhase(kam.cardinal_value.value, false);
		s_tmp = new HashSet<BigInteger>(kam.cardinal_value.members);
		s_tmp.add(member_id);
		iv_tmp = new IntermediateValue(s_tmp, k_tmp);
		logger.fine("Calcolato il nuovo valore cardinale: " + iv_tmp);
		
		/* Crea il nuovo messaggio di key agreement. */
		return new KAMValues(new_int_val, iv_tmp);
		
	}

	/**
	 * Effettua la fase di upflow da membro iniziale:
	 * l'insieme di valori intermedi e' vuoto, crea il valore cardinale iniziale.
	 * @param member_id identificativo del membro del gruppo che sta eseguendo il passo
	 *        corrente della fase di upflow.
	 * @return il primo messaggio di key agreement.
	 * @throws IllegalStateException se la fase di upflow e' fatta con uno stato erroneo
	 *         degli elementi crittografci interessati (ad es. non e' stata generata nessuna
	 *         coppia di chiavi pubblica/privata).
	 */
	private KAMValues startUpflow(BigInteger member_id) throws IllegalStateException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
			
		IntermediateValue iv_tmp;
		Key k_tmp;
		Set<BigInteger> s_tmp;
		
		/* L'insieme dei valori intermedi e' vuoto. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(0);
		logger.finer("Nessun valore intermedio da calcolare.");
		
		/* Il valore cardinale corrisponde alla chiave pubblica corrente. */
		k_tmp = key_pair.getPublic();
		s_tmp = new HashSet<BigInteger>();
		s_tmp.add(member_id);
		iv_tmp = new IntermediateValue(s_tmp, k_tmp); 
		logger.finer("Calcolato il nuovo valore cardinale: " + iv_tmp);
		
		/* Crea il messaggio di key agreement. */
		return new KAMValues(new_int_val, iv_tmp);
		
	}

}
